from __future__ import annotations

import argparse
import importlib.util
import json
import platform
from pathlib import Path

from . import __version__
from .builder import build_region
from .config import load_profiles, load_regions, load_yaml
from .provenance import verify_manifest, write_manifest
from .sources import SourceRegistry
from .theme import resolve_theme
from .verification import verify_generated_file
from .workflow import BuildRequest, execute_build

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

    r = sub.add_parser("regions")
    r.add_argument("--config", type=Path, default=Path("config/regions.yml"))

    m = sub.add_parser("manifest")
    m.add_argument("output", type=Path)
    m.add_argument("root", type=Path)
    m.add_argument("--repo-root", type=Path, default=Path("."))

    v = sub.add_parser("verify")
    v.add_argument("generated_file", type=Path)

    vm = sub.add_parser("verify-manifest")
    vm.add_argument("manifest", type=Path)
    vm.add_argument("root", type=Path)

    b = sub.add_parser("build", aliases=["build-region"])
    b.add_argument("region")
    b.add_argument("--config", type=Path, default=Path("config/regions.yml"))
    b.add_argument("--output", type=Path, default=Path("build/outputs"))
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

    args = p.parse_args()
    if args.cmd == "doctor":
        raise SystemExit(doctor())
    if args.cmd == "regions":
        regions = load_regions(args.config)
        print(json.dumps({k: vars(v) for k, v in regions.items()}, indent=2))
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
    if args.cmd in {"build", "build-region"}:
        regions = load_regions(args.config)
        if args.region not in regions:
            raise SystemExit(f"Unknown region: {args.region}")
        region = regions[args.region]
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
                    output_root=args.output,
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
