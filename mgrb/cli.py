from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__
from .builder import build_region
from .config import load_profiles, load_regions, load_yaml
from .equidistance import EquidistanceParameters, build_equidistance_file
from .layer_registry import LayerRegistry
from .product import ProductBuildSpec
from .provenance import verify_manifest, write_manifest
from .sources import SourceRegistry
from .theme import resolve_theme
from .verification import verify_generated_file
from .workflow import (
    BuildRequest,
    execute_build,
    execute_product_build,
)

ROOT = Path(__file__).resolve().parents[1]


def doctor() -> int:
    modules = ["geopandas", "shapely", "pyproj", "rasterio", "yaml", "jsonschema"]
    try:
        qgis_core = importlib.util.find_spec("qgis.core")
        qgis = bool(qgis_core)
    except (ImportError, ModuleNotFoundError, AttributeError):
        qgis = False
    result = {
        "mgrb": __version__,
        "python": platform.python_version(),
        "modules": {m: bool(importlib.util.find_spec(m)) for m in modules},
        "pyqgis": qgis,
    }
    print(json.dumps(result, indent=2))
    return 0 if all(result["modules"].values()) else 1


def main() -> None:
    p = argparse.ArgumentParser(prog="mgrb")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")

    ui = sub.add_parser("ui")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-open", action="store_true")
    ui.add_argument("--output-root", type=Path)

    r = sub.add_parser("regions")
    r.add_argument("--config", type=Path, default=Path("config/regions.yml"))

    layers = sub.add_parser("layers")
    layers.add_argument("--config", type=Path, default=Path("config/data_layers.yml"))

    m = sub.add_parser("manifest")
    m.add_argument("output", type=Path)
    m.add_argument("root", type=Path)
    m.add_argument("--repo-root", type=Path, default=Path("."))

    v = sub.add_parser("verify")
    v.add_argument("generated_file", type=Path)

    official = sub.add_parser("verify-official")
    official.add_argument("target", type=Path)
    official.add_argument("--receipt", type=Path)
    official.add_argument("--file", type=Path, dest="artifact")
    official.add_argument("--development-key", type=Path)

    vm = sub.add_parser("verify-manifest")
    vm.add_argument("manifest", type=Path)
    vm.add_argument("root", type=Path)

    median = sub.add_parser("median-line")
    median.add_argument("baseline_a", type=Path)
    median.add_argument("baseline_b", type=Path)
    median.add_argument("output", type=Path)
    median.add_argument("--crs", required=True, help="Local metric computation CRS")
    median.add_argument("--sample-spacing-m", type=float, default=5000.0)
    median.add_argument("--balance-tolerance-m", type=float, default=750.0)

    b = sub.add_parser("build", aliases=["build-region"])
    b.add_argument("region", nargs="?")
    b.add_argument("--spec", type=Path, help="Versioned MGRB Build Spec JSON")
    b.add_argument("--validate-spec", action="store_true", help="Validate --spec without building")
    b.add_argument("--config", type=Path, default=Path("config/regions.yml"))
    b.add_argument("--output", default="build/outputs")
    b.add_argument("--output-root", type=Path)
    b.add_argument("--derived-output", type=Path, default=Path("data/derived"))
    b.add_argument("--land", type=Path)
    b.add_argument("--coastline", type=Path)
    b.add_argument("--labels", type=Path)
    b.add_argument("--bathymetry", type=Path)
    b.add_argument("--boundaries", type=Path)
    b.add_argument("--bathy-width", type=int, default=6000)
    b.add_argument("--profile")
    b.add_argument("--theme", default="canonical")
    b.add_argument("--profiles-config", type=Path, default=Path("config/profiles.yml"))
    b.add_argument("--layouts-config", type=Path, default=Path("config/layouts.yml"))
    b.add_argument("--sources-config", type=Path, default=Path("metadata/sources.yml"))
    b.add_argument("--land-source")
    b.add_argument("--coastline-source")
    b.add_argument("--labels-source")
    b.add_argument("--output-name")
    b.add_argument("--no-visible-footer", action="store_true")
    b.add_argument("--from", dest="start_date", type=date.fromisoformat)
    b.add_argument("--to", dest="end_date", type=date.fromisoformat)
    b.add_argument("--actors", default="")
    b.add_argument("--public-data", action="store_true", default=True)
    b.add_argument("--no-public-data", action="store_false", dest="public_data")
    b.add_argument("--local-data", type=Path, action="append", default=[])
    b.add_argument("--offline", action="store_true")
    b.add_argument("--traffic-density", type=Path)
    b.add_argument("--background", default="bathymetry")
    b.add_argument(
        "--maritime-layers",
        default="eez_reference,territorial_sea",
        help="Comma-separated semantic layer IDs",
    )
    b.add_argument("--input", type=Path, action="append", default=[])
    b.add_argument("--include-public-observations", action="store_true")
    b.add_argument(
        "--context-layers",
        default="",
        help="Comma-separated public context layer IDs from `mgrb layers`",
    )
    b.add_argument(
        "--input-kind",
        choices=(
            "TRACK",
            "OFFICIAL_OBSERVATION",
            "EVENT",
            "PORT",
            "CABLE_LANDING_POINT",
            "SUBMARINE_CABLE",
            "OTHER_INFRASTRUCTURE",
        ),
        action="append",
        default=[],
        help=(
            "Semantic kind for each --input/--local-data in order; repeat per file, or "
            "provide once to apply to all (default: TRACK)"
        ),
    )

    args = p.parse_args()
    if args.cmd == "verify-official":
        from .official import verify_target

        result = verify_target(
            args.target,
            receipt_path=args.receipt,
            artifact=args.artifact,
            development_key=args.development_key,
        )
        print(json.dumps(result, indent=2))
        raise SystemExit(
            0
            if result.get("signature_valid")
            and (result.get("file_verified") or result["status"].endswith("FILE_UNCHECKED"))
            else 1
        )
    if args.cmd == "doctor":
        raise SystemExit(doctor())
    if args.cmd == "ui":
        from .ui import serve

        serve(
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
            output_root=args.output_root,
        )
        return
    if args.cmd == "regions":
        regions = load_regions(args.config)
        print(json.dumps({k: vars(v) for k, v in regions.items()}, indent=2))
        return
    if args.cmd == "layers":
        registry = LayerRegistry.load(args.config)
        print(json.dumps(registry.grouped_catalog(), indent=2))
        return
    if args.cmd == "manifest":
        write_manifest(args.root, args.output, args.repo_root)
        print(args.output)
        return
    if args.cmd == "verify":
        result = verify_generated_file(args.generated_file)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    if args.cmd == "verify-manifest":
        errors = verify_manifest(args.root, args.manifest)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        raise SystemExit(1 if errors else 0)
    if args.cmd == "median-line":
        output = build_equidistance_file(
            args.baseline_a,
            args.baseline_b,
            args.output,
            computation_crs=args.crs,
            parameters=EquidistanceParameters(
                sample_spacing_m=args.sample_spacing_m,
                balance_tolerance_m=args.balance_tolerance_m,
            ),
        )
        print(output)
        return
    if args.cmd in {"build", "build-region"}:
        if args.spec:
            from .build_spec import load_build_spec

            allowed = {"--spec", "--validate-spec", "--output-root", "--output-name"}
            overrides = {
                token.split("=", 1)[0]
                for token in sys.argv[1:]
                if token.startswith("--") and token.split("=", 1)[0] not in allowed
            }
            if args.region or overrides:
                p.error(
                    "--spec allows only --validate-spec, --output-root and --output-name; edit choices in the spec"
                )
            spec = load_build_spec(args.spec.resolve(), ROOT)
            if args.validate_spec:
                print(json.dumps({"ok": True, "build_spec": spec.to_dict()}, indent=2))
                return
            result, archive = execute_product_build(
                spec,
                output_root=args.output_root or Path(args.output),
                repository_root=ROOT,
                build_id=args.output_name
                or f"MGRB-{spec.area}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "build_id": result.build_id,
                        "output": str(result.output),
                        "portable_archive": str(archive),
                    },
                    indent=2,
                )
            )
            return
        if args.validate_spec or not args.region:
            p.error("Provide a region or --spec; --validate-spec requires --spec")
        regions = load_regions(args.config)
        if args.region not in regions:
            raise SystemExit(f"Unknown region: {args.region}")
        region = regions[args.region]
        if region.research_preset:
            requested_outputs = args.output if "," in str(args.output) else "paper,qgis,media"
            unknown_outputs = set(requested_outputs.split(",")) - {"paper", "qgis", "media"}
            if unknown_outputs:
                raise SystemExit(f"Unknown maritime output profile(s): {sorted(unknown_outputs)}")
            output_root = args.output_root or (
                Path("build/maritime") if "," in str(args.output) else Path(args.output)
            )
            input_paths = (*args.local_data, *args.input)
            input_kinds = args.input_kind or ["TRACK"]
            if len(input_kinds) not in {1, len(input_paths)}:
                raise SystemExit(
                    "Repeat --input-kind once per input, or provide it once to apply to all"
                )
            resolved_kinds = (
                input_kinds * len(input_paths) if len(input_kinds) == 1 else input_kinds
            )
            product_spec = ProductBuildSpec(
                area=region.name,
                background=args.background,
                maritime_layers=tuple(
                    item.strip() for item in args.maritime_layers.split(",") if item.strip()
                ),
                input_files=tuple(str(path) for path in input_paths),
                input_kinds={
                    str(path.resolve()): kind
                    for path, kind in zip(input_paths, resolved_kinds, strict=True)
                },
                context_layers=tuple(
                    item.strip() for item in args.context_layers.split(",") if item.strip()
                ),
                outputs=tuple(requested_outputs.split(",")),
                include_public_observations=args.include_public_observations,
                visible_footer=not args.no_visible_footer,
                start_date=args.start_date.isoformat() if args.start_date else None,
                end_date=args.end_date.isoformat() if args.end_date else None,
                actors=tuple(item.strip() for item in args.actors.split(",") if item.strip()),
            )
            result, archive = execute_product_build(
                product_spec,
                output_root=output_root,
                repository_root=ROOT,
                build_id=args.output_name
                or f"MGRB-{region.name}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            )
            output_display = (
                result.output.relative_to(ROOT).as_posix()
                if result.output.is_relative_to(ROOT)
                else str(result.output)
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "build_id": result.build_id,
                        "output": output_display,
                        "qgis_project": str(result.qgis_project),
                        "elapsed_seconds": round(result.elapsed_seconds, 3),
                        "outputs": requested_outputs.split(","),
                        "portable_archive": str(archive),
                    },
                    indent=2,
                )
            )
            return
        profiles = load_profiles(args.profiles_config)
        profile_name = args.profile or region.profile
        if profile_name not in profiles:
            raise SystemExit(f"Unknown cartographic profile: {profile_name}")
        if profile_name != region.profile:
            raise SystemExit(
                f"Region {region.name} canonically requires profile {region.profile}; got {profile_name}"
            )
        supplied_inputs = any(
            (args.land, args.coastline, args.labels, args.bathymetry, args.boundaries)
        )
        if not supplied_inputs:
            result = execute_build(
                BuildRequest(
                    region=region.name,
                    profile=profile_name,
                    theme=args.theme,
                    output_root=Path(args.output),
                    build_id=args.output_name,
                    visible_footer=not args.no_visible_footer,
                ),
                ROOT,
            )
            output_display = (
                result.output.relative_to(ROOT).as_posix()
                if result.output.is_relative_to(ROOT)
                else str(result.output)
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "build_id": result.build_id,
                        "output": output_display,
                        "verify": f"mgrb verify {output_display}/{result.build_id}.pdf",
                    },
                    indent=2,
                )
            )
            return
        profile = profiles[profile_name]
        layouts = load_yaml(args.layouts_config).get("layouts", {})
        if profile.layout not in layouts:
            raise SystemExit(f"Missing layout profile: {profile.layout}")
        registry = SourceRegistry.load(args.sources_config)
        selected_sources = []
        land_source = registry.select(region, "land", args.land_source) if args.land else None
        coastline_source = (
            registry.select(region, "coastline", args.coastline_source)
            if args.coastline
            else land_source
        )
        labels_source = (
            registry.select(region, "labels", args.labels_source) if args.labels else None
        )
        layer_map: dict[str, list[str]] = {}
        for layer_name, source in (
            ("land", land_source),
            ("coastline", coastline_source),
            ("labels", labels_source),
        ):
            if source:
                layer_map.setdefault(source.source_id, []).append(layer_name)
        if args.bathymetry:
            layer_map.setdefault("gebco_2026", []).extend(["bathymetry", "depth_contours"])
        for source_id, layers in sorted(layer_map.items()):
            transformations = [
                f"clip to {region.name}",
                f"longitude convention {region.longitude_convention}",
            ]
            selected_sources.append(
                registry.get(source_id).manifest_record(layers, transformations)
            )
        resolved_theme = resolve_theme(args.theme, Path("config/themes"))
        spec = build_region(
            region,
            args.derived_output,
            land=args.land,
            coastline=args.coastline,
            labels=args.labels,
            bathymetry=args.bathymetry,
            boundary_file=args.boundaries,
            bathymetry_width=args.bathy_width,
            output_name=args.output_name,
            profile=vars(profile),
            layout=layouts[profile.layout],
            theme=resolved_theme,
            source_manifest=selected_sources,
            repository_root=Path.cwd(),
            product=load_yaml(ROOT / "config/product.yml")["product"],
            visible_footer=not args.no_visible_footer,
        )
        print(json.dumps(spec, indent=2))
        return


if __name__ == "__main__":
    main()
