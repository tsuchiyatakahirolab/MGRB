from datetime import date

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from mgrb.analytics import (
    distance_to_features,
    low_speed_candidates,
    repeated_area_visits,
    track_coverage_metrics,
    zone_crossing_candidates,
)


def _points() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "observation_id": ["a", "b", "c"],
            "dataset_id": ["d1"] * 3,
            "entity_id": ["v1"] * 3,
            "timestamp_start": [
                "2025-01-01T00:00:00Z",
                "2025-01-01T01:00:00Z",
                "2025-01-01T10:00:00Z",
            ],
            "speed": [2.0, 7.0, 1.0],
        },
        geometry=[Point(120, 20), Point(121, 20), Point(122, 20)],
        crs=4326,
    )


def test_track_coverage_metrics_are_gap_safe_and_requested_fraction_is_bounded() -> None:
    metrics = track_coverage_metrics(
        _points(), requested_start=date(2025, 1, 1), requested_end=date(2025, 1, 2)
    ).iloc[0]
    assert metrics["observation_count"] == 3
    assert metrics["gap_count_over_6h"] == 1
    assert metrics["segment_count"] == 2
    assert 0 <= metrics["requested_time_fraction_observed"] <= 1


def test_transparent_spatial_primitives() -> None:
    points = _points()
    port = gpd.GeoDataFrame({"name": ["p"]}, geometry=[Point(120.1, 20)], crs=4326)
    distances = distance_to_features(points, port, distance_name="distance_to_port_m")
    assert len(distances) == 3
    tracks = gpd.GeoDataFrame(
        {"segment_id": ["s1"]}, geometry=[LineString([(119, 20), (121, 20)])], crs=4326
    )
    zones = gpd.GeoDataFrame({"zone": ["z"]}, geometry=[box(120, 19, 122, 21)], crs=4326)
    assert len(zone_crossing_candidates(tracks, zones)) == 1
    visits = repeated_area_visits(points, zones)
    assert visits.iloc[0]["visit_count"] == 1
    low = low_speed_candidates(points)
    assert len(low) == 2
    assert low["metric_semantics"].str.contains("NOT_BEHAVIOR").all()
