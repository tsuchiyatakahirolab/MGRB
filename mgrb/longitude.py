from __future__ import annotations
from collections.abc import Iterable
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


def lon_to_360(x: float) -> float:
    return x % 360.0


def lon_to_180(x: float) -> float:
    y = ((x + 180.0) % 360.0) - 180.0
    return 180.0 if y == -180.0 and x > 0 else y


def transform_longitudes(geometry: BaseGeometry, convention: str) -> BaseGeometry:
    """Point-wise longitude transformation.

    This is appropriate for already split geometries. Lines crossing the antimeridian
    should first be processed with QGIS `native:antimeridiansplit` in the QGIS build
    stage so that a geodesic split is used rather than a planar guess.
    """
    if convention not in {"180", "360"}:
        raise ValueError("convention must be '180' or '360'")
    fn = lon_to_180 if convention == "180" else lon_to_360
    return transform(
        lambda x, y, z=None: (fn(x), y) if z is None else (fn(x), y, z),
        geometry,
    )


def bbox_360_to_180_parts(
    bbox: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    """Convert a 0..360 bbox into one or two -180..180 source bboxes."""
    xmin, ymin, xmax, ymax = bbox
    if not (0 <= xmin <= 360 and 0 <= xmax <= 360 and xmin < xmax):
        raise ValueError("0..360 bbox must satisfy 0 <= xmin < xmax <= 360")
    if xmax <= 180:
        return [(xmin, ymin, xmax, ymax)]
    if xmin >= 180:
        return [(xmin - 360, ymin, xmax - 360, ymax)]
    return [(xmin, ymin, 180.0, ymax), (-180.0, ymin, xmax - 360.0, ymax)]


def shift_bounds_to_360(bounds: Iterable[float]) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = [float(v) for v in bounds]
    return lon_to_360(xmin), ymin, lon_to_360(xmax), ymax
