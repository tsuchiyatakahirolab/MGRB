from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import LineString

from mgrb.equidistance import EquidistanceParameters, computed_equidistance_reference
from mgrb.importer import inspect_input, normalize_user_input
from mgrb.product import (
    BACKGROUND_PRESETS,
    MARITIME_LAYERS,
    ProductBuildSpec,
    custom_region_defaults,
    product_catalog,
)
from mgrb.ui import create_server

ROOT = Path(__file__).resolve().parents[1]


def _track_csv(path: Path) -> Path:
    pd.DataFrame(
        {
            "MMSI": ["123456789"] * 4,
            "timestamp": [
                "2025-01-01T00:00:00Z",
                "2025-01-01T00:30:00Z",
                "2025-01-01T00:45:00Z",
                "2025-01-01T01:00:00Z",
            ],
            "lat": [22.0, 22.01, 22.02, 22.03],
            "lon": [122.0, 122.01, 122.02, 122.03],
            "seg_id": ["provider-a", "provider-a", "provider-b", "provider-b"],
        }
    ).to_csv(path, index=False)
    return path


def test_product_catalog_covers_required_decisions():
    catalog = product_catalog(ROOT)
    areas = {item["id"] for item in catalog["areas"]}
    assert {
        "taiwan-east",
        "taiwan-south",
        "taiwan-strait",
        "bashi-luzon-strait",
        "east-china-sea",
        "south-china-sea",
        "west_pacific",
        "pacific_360",
        "custom",
    } <= areas
    assert {"bathymetry", "minimal-grayscale", "none"} <= set(BACKGROUND_PRESETS)
    assert {"territorial_sea", "eez_reference", "computed_median"} <= set(MARITIME_LAYERS)


def test_custom_extent_resolves_profile_projection_and_orientation():
    portrait = custom_region_defaults((120.0, 18.0, 123.0, 27.0))
    assert portrait["profile"] == "regional"
    assert portrait["orientation"] == "portrait"
    assert "+proj=laea" in portrait["display_crs"]
    with pytest.raises(ValueError, match="west < east"):
        custom_region_defaults((123.0, 18.0, 120.0, 27.0))


def test_computed_median_is_explicit_non_authoritative_reference():
    result = computed_equidistance_reference(
        LineString([(120.0, 22.0), (120.0, 24.0)]),
        LineString([(122.0, 22.0), (122.0, 24.0)]),
        computation_crs="EPSG:32651",
        source_a="baseline-a.gpkg",
        source_b="baseline-b.gpkg",
        parameters=EquidistanceParameters(
            sample_spacing_m=25_000,
            balance_tolerance_m=2_500,
        ),
    )
    row = result.iloc[0]
    assert row["legal_status"] == "COMPUTED_REFERENCE"
    assert "not an agreed" in row["disclaimer"]
    assert 120.9 < row.geometry.centroid.x < 121.1


def test_schema_detection_and_provider_segment_preservation(tmp_path: Path):
    path = _track_csv(tmp_path / "track.csv")
    inspection = inspect_input(path)
    assert inspection.record_count == 4
    assert inspection.detected_fields["MMSI"] == "MMSI"
    assert inspection.detected_fields["source_segment_id"] == "seg_id"
    assert not inspection.requires_confirmation
    normalized, summary = normalize_user_input(path, build_id="product-import-test")
    assert normalized["entity_id"].nunique() == 1
    assert set(normalized["source_segment_id"]) == {"provider-a", "provider-b"}
    assert summary["track_segments"] == 2


def test_ambiguous_schema_requires_confirmation(tmp_path: Path):
    path = tmp_path / "ambiguous.csv"
    pd.DataFrame(
        {
            "lat": [22.0],
            "latitude": [22.0],
            "lon": [122.0],
            "timestamp": ["2025-01-01T00:00:00Z"],
            "id": ["vessel-a"],
        }
    ).to_csv(path, index=False)
    inspection = inspect_input(path)
    assert inspection.requires_confirmation
    assert any("Ambiguous latitude" in reason for reason in inspection.reasons)


def test_product_spec_state_is_machine_readable_and_valid():
    spec = ProductBuildSpec(
        area="taiwan-east",
        background="minimal-grayscale",
        maritime_layers=("eez_reference",),
        outputs=("preview", "paper", "qgis"),
    )
    spec.validate(ROOT)
    restored = ProductBuildSpec.from_dict(spec.to_dict())
    assert restored == spec


def test_local_ui_catalog_upload_and_preview(tmp_path: Path):
    server = create_server(port=0, root=ROOT, output_root=tmp_path / "outputs")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/catalog") as response:
            catalog = json.load(response)
        assert catalog["defaults"]["area"] == "taiwan-east"

        body = _track_csv(tmp_path / "upload.csv").read_bytes()
        request = urllib.request.Request(
            base + "/api/inspect",
            data=body,
            method="POST",
            headers={"X-MGRB-Filename": "upload.csv"},
        )
        with urllib.request.urlopen(request) as response:
            uploaded = json.load(response)
        assert uploaded["inspection"]["record_count"] == 4
        assert uploaded["qc_summary"]["track_segments"] == 2

        preview_payload = {
            "area": "taiwan-east",
            "background": "bathymetry",
            "maritime_layers": ["eez_reference"],
            "outputs": ["preview"],
            "upload_tokens": [uploaded["token"]],
        }
        request = urllib.request.Request(
            base + "/api/preview",
            data=json.dumps(preview_payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            preview = json.load(response)
        assert preview["ok"]
        assert preview["maritime_layers"] == ["eez_reference"]
        assert preview["inputs"][0]["sample_positions"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
