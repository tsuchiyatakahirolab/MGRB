from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import box
from shapely.ops import transform

from .longitude import bbox_360_to_180_parts


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
    gdf = gdf.copy()
    gdf.geometry = gdf.geometry.map(
        lambda geometry: (
            make_valid(geometry) if geometry is not None and not geometry.is_valid else geometry
        )
    )
    if longitude == "360":
        frames = []
        for source_bbox in bbox_360_to_180_parts(bbox):
            source_clip = box(*source_bbox)
            part = gdf[gdf.intersects(source_clip)].copy()
            if part.empty:
                continue
            part.geometry = part.geometry.intersection(source_clip)
            if source_bbox[0] < 0:
                part.geometry = part.geometry.map(
                    lambda geometry: transform(
                        lambda x, y, z=None: (x + 360.0, y) if z is None else (x + 360.0, y, z),
                        geometry,
                    )
                )
            frames.append(part)
        out = (
            gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=gdf.crs)
            if frames
            else gdf.iloc[0:0].copy()
        )
    elif longitude != "180":
        raise ValueError("longitude must be '180' or '360'")
    else:
        clip_geom = box(*bbox)
        out = gdf[gdf.intersects(clip_geom)].copy()
        if not out.empty:
            out.geometry = out.geometry.intersection(clip_geom)
    if not out.empty:
        out.geometry = out.geometry.map(
            lambda geometry: (
                make_valid(geometry) if geometry is not None and not geometry.is_valid else geometry
            )
        )
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


def write_empty_boundary_layer(
    dst: Path, layer: str = "maritime_boundaries", mode: str = "w"
) -> None:
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
    gdf.to_file(dst, layer=layer, driver="GPKG", mode=mode, index=False)
