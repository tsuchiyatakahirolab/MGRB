from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, transform, unary_union


@dataclass(frozen=True)
class EquidistanceParameters:
    sample_spacing_m: float = 5000.0
    balance_tolerance_m: float = 750.0
    method: str = "MUTUAL_NEAREST_BASELINE_MIDPOINT_REFERENCE"


def _sample(geometry, spacing: float) -> list[Point]:
    lines = list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]
    points = []
    for line in lines:
        count = max(2, math.ceil(line.length / spacing) + 1)
        points.extend(
            line.interpolate(index / (count - 1), normalized=True) for index in range(count)
        )
    return points


def _principal_sort(points: list[Point]) -> list[Point]:
    mean_x = sum(point.x for point in points) / len(points)
    mean_y = sum(point.y for point in points) / len(points)
    xx = sum((point.x - mean_x) ** 2 for point in points)
    yy = sum((point.y - mean_y) ** 2 for point in points)
    xy = sum((point.x - mean_x) * (point.y - mean_y) for point in points)
    angle = 0.5 * math.atan2(2 * xy, xx - yy)
    axis_x, axis_y = math.cos(angle), math.sin(angle)
    return sorted(
        points, key=lambda point: (point.x - mean_x) * axis_x + (point.y - mean_y) * axis_y
    )


def computed_equidistance_reference(
    baseline_a,
    baseline_b,
    *,
    source_crs: str = "EPSG:4326",
    computation_crs: str,
    source_a: str,
    source_b: str,
    parameters: EquidistanceParameters | None = None,
) -> gpd.GeoDataFrame:
    """Create an explicitly non-authoritative median/equidistance reference.

    The method samples both source baselines, forms mutual nearest-point midpoints,
    checks each candidate against the full baseline geometries, and orders retained
    candidates along their principal axis. It is a reproducible cartographic reference,
    not a treaty-delimited or officially declared boundary.
    """
    parameters = parameters or EquidistanceParameters()
    if baseline_a.is_empty or baseline_b.is_empty:
        raise ValueError("Both baseline geometries must be non-empty")
    forward = Transformer.from_crs(source_crs, computation_crs, always_xy=True)
    reverse = Transformer.from_crs(computation_crs, source_crs, always_xy=True)
    projected_a = transform(forward.transform, baseline_a)
    projected_b = transform(forward.transform, baseline_b)
    candidates = []
    for source_point, opposite in (
        *((point, projected_b) for point in _sample(projected_a, parameters.sample_spacing_m)),
        *((point, projected_a) for point in _sample(projected_b, parameters.sample_spacing_m)),
    ):
        other = nearest_points(source_point, opposite)[1]
        candidate = Point((source_point.x + other.x) / 2, (source_point.y + other.y) / 2)
        balance = abs(candidate.distance(projected_a) - candidate.distance(projected_b))
        if balance <= parameters.balance_tolerance_m:
            candidates.append(candidate)
    unique = {(round(point.x, 3), round(point.y, 3)): point for point in candidates}
    ordered = _principal_sort(list(unique.values()))
    if len(ordered) < 2:
        raise ValueError("Baselines did not produce a stable equidistance reference")
    line = transform(reverse.transform, LineString(ordered))
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return gpd.GeoDataFrame(
        [
            {
                "feature_id": "computed-median-1",
                "boundary_type": "computed_median_equidistance_reference",
                "legal_status": "COMPUTED_REFERENCE",
                "method": parameters.method,
                "source_baseline_a": source_a,
                "source_baseline_b": source_b,
                "computation_parameters": json.dumps(asdict(parameters), sort_keys=True),
                "computation_crs": computation_crs,
                "generated_timestamp_utc": timestamp,
                "disclaimer": (
                    "Computed cartographic reference; not an agreed or authoritative "
                    "international boundary"
                ),
                "geometry": line,
            }
        ],
        geometry="geometry",
        crs=source_crs,
    )


def build_equidistance_file(
    baseline_a_path: Path,
    baseline_b_path: Path,
    output: Path,
    *,
    computation_crs: str,
    parameters: EquidistanceParameters | None = None,
) -> Path:
    frame_a = gpd.read_file(baseline_a_path).to_crs(4326)
    frame_b = gpd.read_file(baseline_b_path).to_crs(4326)
    result = computed_equidistance_reference(
        unary_union(frame_a.geometry),
        unary_union(frame_b.geometry),
        computation_crs=computation_crs,
        source_a=baseline_a_path.name,
        source_b=baseline_b_path.name,
        parameters=parameters,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(output, layer="computed_median", driver="GPKG", index=False)
    return output
