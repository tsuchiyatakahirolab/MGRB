from __future__ import annotations

from datetime import date
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def track_coverage_metrics(
    points: gpd.GeoDataFrame,
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
    gap_hours: float = 6.0,
) -> pd.DataFrame:
    columns = [
        "dataset_id",
        "entity_id",
        "observation_count",
        "first_timestamp",
        "last_timestamp",
        "temporal_span_hours",
        "mean_observations_per_day",
        "gap_count_over_6h",
        "maximum_gap_hours",
        "segment_count",
        "requested_time_fraction_observed",
    ]
    if points.empty:
        return pd.DataFrame(columns=columns)
    frame = points.copy()
    if "dataset_id" not in frame:
        frame["dataset_id"] = frame.get("source_name", "dataset").astype(str)
    frame["_time"] = pd.to_datetime(frame["timestamp_start"], errors="coerce", utc=True)
    records: list[dict[str, Any]] = []
    for (dataset_id, entity_id), group in frame.dropna(subset=["_time"]).groupby(
        ["dataset_id", "entity_id"], dropna=False
    ):
        times = group["_time"].sort_values().drop_duplicates()
        gaps = times.diff().dt.total_seconds().div(3600).dropna()
        span_hours = max(0.0, (times.max() - times.min()).total_seconds() / 3600)
        requested_fraction = None
        if requested_start and requested_end and requested_end >= requested_start:
            requested_hours = ((requested_end - requested_start).days + 1) * 24
            requested_fraction = min(1.0, span_hours / requested_hours)
        records.append(
            {
                "dataset_id": str(dataset_id),
                "entity_id": str(entity_id),
                "observation_count": len(group),
                "first_timestamp": times.min().isoformat(),
                "last_timestamp": times.max().isoformat(),
                "temporal_span_hours": round(span_hours, 6),
                "mean_observations_per_day": round(len(group) / max(span_hours / 24, 1), 6),
                "gap_count_over_6h": int((gaps > gap_hours).sum()),
                "maximum_gap_hours": round(float(gaps.max()), 6) if len(gaps) else 0.0,
                "segment_count": int((gaps > gap_hours).sum() + 1),
                "requested_time_fraction_observed": (
                    round(requested_fraction, 6) if requested_fraction is not None else None
                ),
            }
        )
    return pd.DataFrame(records, columns=columns)


def distance_to_features(
    points: gpd.GeoDataFrame,
    features: gpd.GeoDataFrame,
    *,
    distance_name: str,
) -> pd.DataFrame:
    rows = []
    if points.empty or features.empty:
        return pd.DataFrame(columns=["observation_id", distance_name, "nearest_feature_index"])
    metric_crs = points.estimate_utm_crs() or "EPSG:3857"
    metric_points = points.to_crs(metric_crs)
    metric_features = features.to_crs(metric_crs)
    for index, point in metric_points.geometry.items():
        distances = metric_features.geometry.distance(point)
        nearest = distances.idxmin()
        rows.append(
            {
                "observation_id": points.loc[index].get("observation_id", str(index)),
                distance_name: round(float(distances.loc[nearest]), 3),
                "nearest_feature_index": str(nearest),
            }
        )
    return pd.DataFrame(rows)


def zone_crossing_candidates(tracks: gpd.GeoDataFrame, zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    records: list[dict[str, Any]] = []
    if tracks.empty or zones.empty:
        return gpd.GeoDataFrame(
            columns=["segment_id", "zone_index", "metric_semantics", "geometry"],
            geometry="geometry",
            crs=4326,
        )
    tracks = tracks.to_crs(4326)
    zones = zones.to_crs(4326)
    for _, track in tracks.iterrows():
        for zone_index, zone in zones.iterrows():
            boundary = zone.geometry.boundary
            intersection = track.geometry.intersection(boundary)
            for point in _intersection_points(intersection):
                records.append(
                    {
                        "segment_id": track.get("segment_id"),
                        "zone_index": str(zone_index),
                        "metric_semantics": "DESCRIPTIVE_CROSSING_CANDIDATE",
                        "geometry": point,
                    }
                )
    if not records:
        return gpd.GeoDataFrame(
            columns=["segment_id", "zone_index", "metric_semantics", "geometry"],
            geometry="geometry",
            crs=4326,
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=4326)


def _intersection_points(geometry) -> list[Point]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type == "MultiPoint":
        return list(geometry.geoms)
    if hasattr(geometry, "geoms"):
        points: list[Point] = []
        for item in geometry.geoms:
            points.extend(_intersection_points(item))
        return points
    coordinates = list(geometry.coords) if hasattr(geometry, "coords") else []
    return [Point(coordinates[0])] if coordinates else []


def repeated_area_visits(points: gpd.GeoDataFrame, areas: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    if points.empty or areas.empty:
        return pd.DataFrame(columns=["entity_id", "area_index", "visit_count", "point_count"])
    for entity_id, group in points.sort_values("timestamp_start").groupby("entity_id"):
        for area_index, area in areas.iterrows():
            area_geometry = area.geometry
            inside = group.geometry.apply(
                lambda geometry, boundary=area_geometry: bool(geometry.within(boundary))
            )
            visits = int((inside & ~inside.shift(fill_value=False)).sum())
            if inside.any():
                rows.append(
                    {
                        "entity_id": str(entity_id),
                        "area_index": str(area_index),
                        "visit_count": visits,
                        "point_count": int(inside.sum()),
                        "metric_semantics": "DESCRIPTIVE_PRESENCE_NOT_INTENT",
                    }
                )
    return pd.DataFrame(rows)


def low_speed_candidates(points: gpd.GeoDataFrame, threshold_knots: float = 3.0) -> pd.DataFrame:
    if "speed" not in points:
        return pd.DataFrame(
            columns=["observation_id", "entity_id", "speed_knots", "metric_semantics"]
        )
    speed = pd.to_numeric(points["speed"], errors="coerce")
    selected = points.loc[speed.between(0, threshold_knots)].copy()
    return pd.DataFrame(
        {
            "observation_id": selected["observation_id"],
            "entity_id": selected["entity_id"],
            "speed_knots": speed.loc[selected.index],
            "metric_semantics": "LOW_SPEED_CANDIDATE_NOT_BEHAVIOR_CLASSIFICATION",
        }
    )
