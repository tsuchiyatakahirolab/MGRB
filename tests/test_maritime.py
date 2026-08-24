from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import Point

from mgrb.adapters import WorldBankTrafficDensityAdapter, evidence_adapter_catalog
from mgrb.config import load_regions
from mgrb.evidence import QualityControlConfig, normalize_evidence, quality_control, read_evidence
from mgrb.research_package import (
    ResearchBuildRequest,
    normalize_actor_names,
    prepare_research_package,
)
from mgrb.vessels import VesselRegistry

ROOT = Path(__file__).resolve().parents[1]


def _registry() -> VesselRegistry:
    return VesselRegistry.load(
        ROOT / "metadata" / "vessels-v0.1.yml",
        ROOT / "schema" / "vessel_registry.schema.json",
    )


def test_research_area_presets_resolve_gis_defaults():
    regions = load_regions(ROOT / "config" / "regions.yml")
    for name in ("taiwan-east", "taiwan-south"):
        region = regions[name]
        assert region.research_preset
        assert region.display_crs.startswith("+proj=laea")
        assert region.base_region == "taiwan_east_south"
        assert region.default_actors == ("PLAN", "CCG", "RESEARCH_SURVEY", "FISHING")


def test_registry_alias_and_identifier_resolution_are_deterministic():
    registry = _registry()
    assert registry.resolve({"vessel_name": "Jiangkai II 533"}).entity_id == "plan-jiangkai2-533"
    assert registry.resolve({"hull_number": "796"}).entity_id == "plan-dongdiao-796"
    assert registry.resolve({"vessel_name": "山东舰"}).entity_id == "plan-shandong-17"
    assert normalize_actor_names(("plan", "coast guard", "research", "fishing")) == (
        "PLAN",
        "CCG",
        "RESEARCH_SURVEY",
        "FISHING",
    )


def test_synthetic_raw_ais_qc_and_segmentation():
    evidence = read_evidence(
        ROOT / "tests" / "fixtures" / "maritime" / "synthetic_ais.csv",
        _registry(),
        build_id="synthetic-qc",
        source_type="AIS",
        license_text="CC0-1.0 synthetic test fixture",
        attribution="Synthetic MGRB test fixture",
    )
    result = quality_control(evidence, QualityControlConfig())
    flags = set(result.quality_flags["flag"])
    assert {
        "DUPLICATE_OBSERVATION",
        "INVALID_COORDINATE",
        "MISSING_TIME",
        "MALFORMED_MMSI",
        "IMPOSSIBLE_SPEED",
        "LARGE_OBSERVATION_GAP",
    } <= flags
    assert len(result.excluded_points) == 5
    assert len(result.gaps) == 1
    assert set(result.track_segments["segment_type"]) == {"OBSERVED_TRACK"}
    assert result.track_segments.iloc[0]["point_count"] == 2


def test_official_observations_never_become_observed_track():
    source = pd.read_csv(ROOT / "metadata" / "public-observations-v0.1.csv", dtype=str)
    normalized = normalize_evidence(
        source,
        _registry(),
        build_id="official-test",
        source_type="OFFICIAL_OBSERVATION",
        source_name="public seed",
        license_text="source-specific",
        attribution="per-record source",
    )
    result = quality_control(normalized)
    assert "OBSERVED_TRACK" not in set(result.track_segments["segment_type"])
    assert set(result.track_segments["segment_type"]) == {"INFERRED_CONNECTION"}
    map_derived = result.cleaned_points[
        result.cleaned_points["observation_method"] == "MAP_DERIVED_POSITION"
    ]
    assert len(map_derived) == 1
    assert map_derived.iloc[0]["position_confidence"] == "LOW"
    assert float(map_derived.iloc[0]["position_uncertainty_m"]) >= 10_000


def test_geojson_byo_normalization_preserves_local_reference(tmp_path: Path):
    path = tmp_path / "local-evidence.geojson"
    gpd.GeoDataFrame(
        {
            "timestamp": ["2025-01-01T00:00:00Z"],
            "ship_name": ["PLAN 533"],
        },
        geometry=[Point(122.0, 24.0)],
        crs=4326,
    ).to_file(path, driver="GeoJSON")
    loaded = read_evidence(path, _registry(), build_id="byo-test")
    assert loaded.iloc[0]["entity_id"] == "plan-jiangkai2-533"
    assert loaded.iloc[0]["source_type"] == "USER_SUPPLIED"
    assert loaded.iloc[0]["raw_record_reference"] == str(path.resolve())


def test_adapter_catalog_and_large_source_fail_explicitly(tmp_path: Path):
    catalog = evidence_adapter_catalog()
    assert {"global_fishing_watch", "japan_official", "taiwan_official", "byo"} <= set(catalog)
    try:
        WorldBankTrafficDensityAdapter().require_cache(tmp_path / "missing.tif")
    except RuntimeError as exc:
        assert "not cached" in str(exc)
    else:
        raise AssertionError("Unavailable source must not be silently substituted")


def test_public_observation_seed_contains_no_unsourced_militia_label():
    records = pd.read_csv(ROOT / "metadata" / "public-observations-v0.1.csv")
    assert "MARITIME_MILITIA" not in set(records["actor_type"])
    assert records["source_url"].str.startswith("https://").all()
    registry_payload = json.loads(
        json.dumps(
            __import__("yaml").safe_load(
                (ROOT / "metadata" / "vessels-v0.1.yml").read_text(encoding="utf-8")
            )
        )
    )
    assert "MARITIME_MILITIA" not in {item["actor_type"] for item in registry_payload["records"]}


def test_offline_package_has_portable_data_and_manifests(monkeypatch, tmp_path: Path):
    def fake_copy_base(_root: Path, _request: ResearchBuildRequest, package_data: Path) -> dict:
        base = package_data / "base.gpkg"
        point = gpd.GeoDataFrame(
            {"name": ["fixture"]}, geometry=[Point(122.0, 23.0)], crs=4326
        )
        for layer in ("land", "coastline", "labels", "maritime_boundaries"):
            point.to_file(base, layer=layer, driver="GPKG", mode="a" if base.exists() else "w")
        with rasterio.open(
            package_data / "bathymetry.tif",
            "w",
            driver="GTiff",
            width=4,
            height=4,
            count=1,
            dtype="int16",
            crs="EPSG:4326",
            transform=from_bounds(118, 18, 126, 27, 4, 4),
        ) as dataset:
            dataset.write(pd.DataFrame([[-1000] * 4] * 4).to_numpy(dtype="int16"), 1)
        return {
            "sources": [
                {
                    "source_id": "synthetic-public-base-test-only",
                    "provider": "MGRB test",
                    "dataset": "synthetic test base",
                    "license": "CC0-1.0",
                    "commercial_use_known": True,
                    "redistribution_allowed": True,
                }
            ]
        }

    monkeypatch.setattr("mgrb.research_package._copy_base_data", fake_copy_base)
    result = prepare_research_package(
        ResearchBuildRequest(
            area="taiwan-east",
            output_root=tmp_path,
            build_id="offline-package-test",
            live_sources=False,
        ),
        ROOT,
    )
    package = result.package_dir
    for relative in (
        "data/base.gpkg",
        "data/maritime.gpkg",
        "data/vessels.gpkg",
        "data/observations.gpkg",
        "data/tracks.gpkg",
        "data/events.gpkg",
        "data/bathymetry.tif",
        "metadata/mgrb-build.json",
        "metadata/mgrb-source-manifest.json",
        "metadata/mgrb-style-manifest.json",
        "metadata/license_manifest.csv",
        "metadata/provenance.json",
        "metadata/research-spec.json",
    ):
        assert (package / relative).exists(), relative
    assert list((package / "raw").iterdir()) == [package / "raw" / "README.md"]
    spec = json.loads((package / "metadata" / "research-spec.json").read_text())
    assert all(not Path(value).is_absolute() for value in spec["files"].values() if value)
    assert not spec["availability"]["marine_regions"]
    assert "UNAVAILABLE_OFFLINE_MODE" in (
        package / "metadata" / "mgrb-source-manifest.json"
    ).read_text()
