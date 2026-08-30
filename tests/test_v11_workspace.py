from __future__ import annotations

from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from mgrb.config import load_regions
from mgrb.evidence import QualityControlConfig, normalize_evidence, quality_control
from mgrb.product import ProductBuildSpec
from mgrb.research_package import ResearchBuildRequest, _filter_events
from mgrb.vessels import VesselRegistry
from mgrb.workflow import make_portable_zip

ROOT = Path(__file__).resolve().parents[1]


def test_separate_datasets_are_never_joined_as_one_track() -> None:
    loaded = pd.DataFrame(
        {
            "entity_id": ["same-vessel", "same-vessel"],
            "timestamp_start": ["2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z"],
            "latitude": [20.0, 20.01],
            "longitude": [120.0, 120.01],
            "actor_type": ["UNKNOWN", "UNKNOWN"],
        }
    )
    points = normalize_evidence(
        loaded,
        VesselRegistry([]),
        build_id="multi-test",
        source_type="USER_SUPPLIED",
        source_name="two-inputs",
        license_text="test-only",
        attribution="test-only",
    )
    points["dataset_id"] = ["dataset-a", "dataset-b"]
    result = quality_control(points, QualityControlConfig())
    assert result.track_segments.empty


def test_event_time_filter_matches_product_period() -> None:
    events = gpd.GeoDataFrame(
        {
            "event_id": ["before", "inside", "after"],
            "start_time": [
                "2025-12-31T12:00:00Z",
                "2026-01-15T12:00:00Z",
                "2026-02-01T00:00:00Z",
            ],
        },
        geometry=[Point(122, 24), Point(122, 24), Point(122, 24)],
        crs=4326,
    )
    request = ResearchBuildRequest(
        area="taiwan-east",
        output_root=Path("unused"),
        build_id="period-test",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    region = load_regions(ROOT / "config" / "regions.yml")["taiwan-east"]
    filtered = _filter_events(events, region, request)
    assert filtered["event_id"].tolist() == ["inside"]


def test_product_spec_carries_context_and_semantic_input_kind() -> None:
    spec = ProductBuildSpec(
        area="taiwan-east",
        input_files=("official.csv",),
        input_kinds={"official.csv": "OFFICIAL_OBSERVATION"},
        context_layers=("nga_world_port_index",),
        start_date="2026-01-01",
        end_date="2026-12-31",
    )
    spec.validate(ROOT)
    assert ProductBuildSpec.from_dict(spec.to_dict()) == spec


def test_portable_zip_runs_public_private_firewall(tmp_path: Path) -> None:
    package = tmp_path / "package"
    private_file = package / "browser-profile" / "Default" / "Cookies"
    private_file.parent.mkdir(parents=True)
    private_file.write_text("must never package", encoding="utf-8")
    with pytest.raises(RuntimeError, match="PUBLIC_PRIVATE_FIREWALL_BLOCKED"):
        make_portable_zip(package)
    assert not package.with_suffix(".zip").exists()
