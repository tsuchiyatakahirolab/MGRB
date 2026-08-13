from __future__ import annotations
import argparse
import importlib.util
import json
import platform
from pathlib import Path
from . import __version__
from .builder import build_region
from .config import load_regions
from .provenance import write_manifest, verify_manifest


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
    v.add_argument("manifest", type=Path)
    v.add_argument("root", type=Path)

    b = sub.add_parser("build-region")
    b.add_argument("region")
    b.add_argument("--config", type=Path, default=Path("config/regions.yml"))
    b.add_argument("--output", type=Path, default=Path("data/derived"))
    b.add_argument("--land", type=Path)
    b.add_argument("--coastline", type=Path)
    b.add_argument("--bathymetry", type=Path)
    b.add_argument("--boundaries", type=Path)
    b.add_argument("--bathy-width", type=int, default=6000)

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
        errors = verify_manifest(args.root, args.manifest)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        raise SystemExit(1 if errors else 0)
    if args.cmd == "build-region":
        regions = load_regions(args.config)
        if args.region not in regions:
            raise SystemExit(f"Unknown region: {args.region}")
        spec = build_region(
            regions[args.region],
            args.output,
            land=args.land,
            coastline=args.coastline,
            bathymetry=args.bathymetry,
            boundary_file=args.boundaries,
            bathymetry_width=args.bathy_width,
        )
        print(json.dumps(spec, indent=2))
        return


if __name__ == "__main__":
    main()
