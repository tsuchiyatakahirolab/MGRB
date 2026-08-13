from __future__ import annotations
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box
from .longitude import transform_longitudes


def _read(src: Path, layer: str | None = None) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(src, layer=layer if layer else None)
    if gdf.crs is None:
        raise ValueError(f"Input layer has no CRS: {src}")
    return gdf.to_crs(4326)


def clip_vector(
    src: Path,
    dst: Path,
    layer: str | None,
    bbox: tuple[float, float, float, float],
    longitude: str = "180",
    output_layer: str | None = None,
    mode: str = "w",
) -> int:
    gdf = _read(src, layer)
    if longitude == "360":
        gdf = gdf.copy()
        gdf.geometry = gdf.geometry.map(
            lambda g: transform_longitudes(g, "360") if g is not None else g
        )
    elif longitude != "180":
        raise ValueError("longitude must be '180' or '360'")

    xmin, ymin, xmax, ymax = bbox
    clip_geom = box(xmin, ymin, xmax, ymax)
    out = gdf[gdf.intersects(clip_geom)].copy()
    if not out.empty:
        out.geometry = out.geometry.intersection(clip_geom)
        out = out[~out.geometry.is_empty]
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(
        dst,
        layer=output_layer or layer or "layer",
        driver="GPKG",
        mode=mode,
        index=False,
    )
    return len(out)


def write_empty_boundary_layer(dst: Path, layer: str = "maritime_boundaries") -> None:
    columns = {
        "source_id": "string",
        "source_date": "string",
        "boundary_type": "string",
        "legal_status": "string",
        "claimant": "string",
        "counterparty": "string",
        "citation": "string",
        "notes": "string",
    }
    gdf = gpd.GeoDataFrame({name: [] for name in columns}, geometry=[], crs="EPSG:4326")
    dst.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(dst, layer=layer, driver="GPKG", index=False)
