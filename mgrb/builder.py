from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json
import shutil
from .config import Region
from .raster import clip_raster, clip_raster_360
from .vector import clip_vector, write_empty_boundary_layer


def build_region(
    region: Region,
    output_dir: Path,
    *,
    land: Path | None = None,
    coastline: Path | None = None,
    bathymetry: Path | None = None,
    boundary_file: Path | None = None,
    bathymetry_width: int | None = 6000,
) -> dict:
    region_dir = output_dir / region.name
    region_dir.mkdir(parents=True, exist_ok=True)
    gpkg = region_dir / "base.gpkg"
    if gpkg.exists():
        gpkg.unlink()

    counts = {}
    mode = "w"
    if land:
        counts["land"] = clip_vector(
            land, gpkg, None, region.bbox, region.longitude_convention, "land", mode
        )
        mode = "a"
    if coastline:
        counts["coastline"] = clip_vector(
            coastline, gpkg, None, region.bbox, region.longitude_convention, "coastline", mode
        )
        mode = "a"
    if boundary_file:
        counts["maritime_boundaries"] = clip_vector(
            boundary_file,
            gpkg,
            None,
            region.bbox,
            region.longitude_convention,
            "maritime_boundaries",
            mode,
        )
    elif not gpkg.exists():
        write_empty_boundary_layer(gpkg)

    bathy_out = None
    if bathymetry:
        bathy_out = region_dir / "bathymetry.tif"
        if region.longitude_convention == "360":
            clip_raster_360(bathymetry, bathy_out, region.bbox, bathymetry_width)
        else:
            clip_raster(bathymetry, bathy_out, region.bbox, bathymetry_width)

    spec = {
        "region": asdict(region),
        "files": {
            "base_gpkg": str(gpkg.relative_to(output_dir)) if gpkg.exists() else None,
            "bathymetry": str(bathy_out.relative_to(output_dir)) if bathy_out else None,
        },
        "feature_counts": counts,
    }
    (region_dir / "project-spec.json").write_text(
        json.dumps(spec, indent=2) + "\n", encoding="utf-8"
    )
    return spec


def clean_output(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
