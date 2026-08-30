from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import Point

from mgrb.adapters import (
    PangaeaXueLong2012Adapter,
    ScsdiSouthChinaSeaEventsAdapter,
    WorldBankTrafficDensityAdapter,
    evidence_adapter_catalog,
)
from mgrb.cartography import select_scale_interval_km
from mgrb.config import load_regions
from mgrb.evidence import (
    QualityControlConfig,
    normalize_evidence,
    quality_control,
    read_evidence,
    validate_segment_entity_integrity,
)
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
        assert region.media_title
        assert region.orientation_labels

    rich = regions["xue-long-arctic-2012"]
    assert rich.public_evidence_sources == ("pangaea_xue_long_2012",)
    assert rich.default_actors == ("RESEARCH_SURVEY",)
    flagship = regions["south-china-sea"]
    assert flagship.public_evidence_sources == ("scsdi_dataverse_v1",)
    assert flagship.media_title == "South China Sea Maritime Evidence"


def test_scale_bar_uses_rounded_kilometre_intervals():
    assert select_scale_interval_km(500.0) == 25.0
    assert select_scale_interval_km(600.0) == 50.0
    assert select_scale_interval_km(1500.0) == 100.0
    with pytest.raises(ValueError):
        select_scale_interval_km(0)


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


def test_segment_entity_integrity_accepts_same_entity_and_rejects_cross_entity():
    valid = pd.DataFrame(
        [
            {
                "segment_id": "seg-valid",
                "entity_id": "vessel-a",
                "start_entity_id": "vessel-a",
                "end_entity_id": "vessel-a",
                "segment_type": "INFERRED_CONNECTION",
            }
        ]
    )
    validate_segment_entity_integrity(valid)
    invalid = valid.copy()
    invalid.loc[0, "end_entity_id"] = "vessel-b"
    with pytest.raises(ValueError, match="Cross-entity"):
        validate_segment_entity_integrity(invalid)


def test_missing_entity_identity_does_not_produce_route():
    normalized = normalize_evidence(
        pd.DataFrame(
            {
                "timestamp_start": ["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"],
                "latitude": [22.0, 22.1],
                "longitude": [122.0, 122.1],
                "vessel_name": ["unresolved vessel", "unresolved vessel"],
            }
        ),
        _registry(),
        build_id="missing-identity",
        source_type="OFFICIAL_OBSERVATION",
        source_name="identity test",
        license_text="test-only",
        attribution="test-only",
    )
    result = quality_control(normalized)
    assert result.cleaned_points.empty
    assert result.track_segments.empty
    assert "MISSING_VESSEL_IDENTITY" in set(result.quality_flags["flag"])


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


def test_world_bank_cached_raster_is_subset_and_log_transformed(tmp_path: Path):
    source = tmp_path / "world-bank-density.tif"
    values = pd.DataFrame([[0, 1, 3, 7], [1, 3, 7, 15]] * 2).to_numpy(dtype="int32")
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="int32",
        crs="EPSG:4326",
        transform=from_bounds(118, 18, 126, 26, 4, 4),
        nodata=2147483647,
    ) as dataset:
        dataset.write(values, 1)
    output = tmp_path / "subset.tif"
    details = WorldBankTrafficDensityAdapter().subset(
        source, (120, 20, 124, 24), output, buffer_degrees=0
    )
    assert output.exists()
    assert details["transform"] == "log1p"
    assert details["source_sha256"] != details["subset_sha256"]
    with rasterio.open(output) as dataset:
        assert dataset.tags()["MGRB_SOURCE_ID"] == "world_bank_shipping_density_2021"
        assert dataset.read(1).max() < values.max()


def test_world_bank_subset_mosaics_across_antimeridian(tmp_path: Path):
    source = tmp_path / "global-density.tif"
    values = np.tile(np.arange(1, 37, dtype="int32"), (2, 1))
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=36,
        height=2,
        count=1,
        dtype="int32",
        crs="EPSG:4326",
        transform=from_bounds(-180, 60, 180, 80, 36, 2),
        nodata=2147483647,
    ) as dataset:
        dataset.write(values, 1)
    output = tmp_path / "antimeridian-subset.tif"
    details = WorldBankTrafficDensityAdapter().subset(
        source, (170, 62, 190, 78), output, buffer_degrees=0
    )
    assert details["subset_bbox"] == [170, 62, 190, 78]
    with rasterio.open(output) as dataset:
        assert dataset.bounds.left <= 170
        assert dataset.bounds.right >= 190
        assert dataset.tags()["MGRB_LONGITUDE_CONVENTION"] == "0..360"


def test_world_bank_archive_subset_cache_reports_miss_then_hit(tmp_path: Path):
    tif = tmp_path / "shipdensity_global.tif"
    values = np.tile(np.arange(1, 17, dtype="int32"), (8, 1))
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        width=16,
        height=8,
        count=1,
        dtype="int32",
        crs="EPSG:4326",
        transform=from_bounds(116, 16, 132, 24, 16, 8),
        nodata=2147483647,
    ) as dataset:
        dataset.write(values, 1)
    archive = tmp_path / "density.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(tif, "shipdensity_global.tif")
    first = tmp_path / "first.tif"
    second = tmp_path / "second.tif"
    adapter = WorldBankTrafficDensityAdapter()
    cold = adapter.subset(archive, (120, 18, 124, 22), first, buffer_degrees=0)
    warm = adapter.subset(archive, (120, 18, 124, 22), second, buffer_degrees=0)
    assert cold["cache_hit"] is False
    assert warm["cache_hit"] is True
    assert cold["subset_sha256"] == warm["subset_sha256"]


def test_pangaea_public_track_adapter_ingests_documented_positions(tmp_path: Path):
    sample = tmp_path / "pangaea.tsv"
    sample.write_text(
        "/* public adapter test sample */\n"
        "Date/Time\tLongitude\tLatitude\tDepth water [m]\n"
        "2012-07-17T17:38\t-168.49249\t65.00750\t5.0\n"
        "2012-07-17T17:41\t-168.50114\t65.01785\t5.0\n",
        encoding="utf-8",
    )
    frame = PangaeaXueLong2012Adapter().parse(sample)
    assert len(frame) == 2
    assert set(frame["source_type"]) == {"PUBLIC_TRACK"}
    normalized = normalize_evidence(
        frame,
        _registry(),
        build_id="pangaea-ingestion",
        source_type="PUBLIC_TRACK",
        source_name="PANGAEA 891818",
        license_text="CC BY 3.0",
        attribution="PANGAEA",
    )
    result = quality_control(normalized)
    assert len(result.cleaned_points) == 2
    assert set(result.track_segments["segment_type"]) == {"OBSERVED_TRACK"}
    assert result.track_segments.iloc[0]["start_entity_id"] == "research-xue-long"
    assert result.track_segments.iloc[0]["end_entity_id"] == "research-xue-long"


def test_scsdi_adapter_preserves_event_semantics_and_uncertainty(tmp_path: Path):
    sample = tmp_path / "scsdi.csv"
    sample.write_text(
        "event_id,event_id_cnty,event_date,year,time_precision,latitude,longitude,"
        "level,radius,note_on_location,location,source,notes,number_of_report\n"
        "CNPH_200101,CN/PH,01/01/20,2020,,12.5,116.2,2,0.4,reported,"
        "South China Sea,https://example.test/report,public event,3\n",
        encoding="cp1252",
    )
    events = ScsdiSouthChinaSeaEventsAdapter().parse(sample)
    assert len(events) == 1
    assert events.iloc[0]["source_type"] == "PUBLIC_EVENT"
    assert events.iloc[0]["event_type"] == "GEOCODED_DISPUTE_EVENT"
    assert events.iloc[0]["confidence"] == "MEDIUM"
    assert events.iloc[0]["location_precision_level"] == 2
    assert events.iloc[0]["uncertainty_radius_degrees"] == pytest.approx(0.4)
    assert events.iloc[0]["license"] == "CC0 1.0"


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
    def fake_copy_base(
        _root: Path,
        _request: ResearchBuildRequest,
        _region,
        package_data: Path,
    ) -> dict:
        base = package_data / "base.gpkg"
        point = gpd.GeoDataFrame({"name": ["fixture"]}, geometry=[Point(122.0, 23.0)], crs=4326)
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
        "data/context.gpkg",
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
    assert (
        "UNAVAILABLE_OFFLINE_MODE"
        in (package / "metadata" / "mgrb-source-manifest.json").read_text()
    )
