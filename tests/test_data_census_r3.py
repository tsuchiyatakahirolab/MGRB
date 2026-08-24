from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "docs" / "data-census"
REQUIRED = {
    "CHINA_MARITIME_TRACK_SOURCE_CENSUS.md",
    "SOURCE_SCORECARD.csv",
    "SOURCE_COVERAGE_MATRIX.csv",
    "SOURCE_LICENSE_MATRIX.csv",
    "SEARCH_LOG.csv",
    "VESSEL_SOURCE_CROSSWALK.csv",
    "RETRIEVAL_TEST_RESULTS.csv",
    "COVERAGE_GAPS.md",
    "R3_CONNECTOR_PRIORITY.md",
}


def read_csv(name: str) -> list[dict[str, str]]:
    with (CENSUS / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_required_census_artifacts_exist() -> None:
    assert REQUIRED <= {path.name for path in CENSUS.iterdir()}
    for stem in (
        "SOURCE_SCORECARD",
        "SOURCE_COVERAGE_MATRIX",
        "SOURCE_LICENSE_MATRIX",
        "SEARCH_LOG",
        "VESSEL_SOURCE_CROSSWALK",
        "RETRIEVAL_TEST_RESULTS",
    ):
        assert (CENSUS / f"{stem}.json").is_file()


def test_scorecard_has_complete_decision_fields_and_unique_ids() -> None:
    rows = read_csv("SOURCE_SCORECARD.csv")
    assert len(rows) >= 40
    required = {
        "source_id",
        "provider",
        "product",
        "url",
        "languages",
        "actor_families",
        "evidence_type",
        "geographic_coverage",
        "temporal_coverage",
        "update_cadence_or_lag",
        "identity_fields",
        "spatial_density_or_resolution",
        "temporal_resolution",
        "coordinate_precision",
        "processing_level",
        "quality_flags",
        "uncertainty_model",
        "format",
        "qgis_readiness",
        "access_class",
        "license_or_terms",
        "attribution_required",
        "redistribution",
        "commercial_use",
        "recommended_citation",
        "production_suitability",
        "connector_priority",
        "default_eligible",
        "decision_reason",
    }
    assert required <= set(rows[0])
    ids = [row["source_id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert {row["connector_priority"] for row in rows} <= {"P0", "P1", "P2", "P3", "REJECT"}
    assert all(row["url"].startswith("https://") for row in rows)


def test_default_sources_have_successful_real_retrievals() -> None:
    score = read_csv("SOURCE_SCORECARD.csv")
    tests = read_csv("RETRIEVAL_TEST_RESULTS.csv")
    successful = {
        row["source_id"]
        for row in tests
        if row["access_result"].startswith("SUCCESS") and row["decision"] not in {"REJECT_ARTIFACT"}
    }
    defaults = {row["source_id"] for row in score if row["default_eligible"] == "YES"}
    assert defaults
    assert defaults <= successful


def test_commercial_sources_are_byo_p3_and_never_default() -> None:
    rows = read_csv("SOURCE_SCORECARD.csv")
    commercial = [row for row in rows if row["access_class"] == "COMMERCIAL"]
    assert commercial
    assert all(row["connector_priority"] == "P3" for row in commercial)
    assert all(row["default_eligible"] == "NO" for row in commercial)


def test_retrieval_results_record_positive_and_negative_content_gates() -> None:
    rows = read_csv("RETRIEVAL_TEST_RESULTS.csv")
    assert len(rows) >= 10
    assert any(row["expected_hash_match"] == "YES" for row in rows)
    assert any(row["access_result"] == "LOGIN_WALL" for row in rows)
    assert any(row["decision"] == "REJECT_ARTIFACT" for row in rows)
    assert any(row["qgis_or_geopandas_test"].startswith("loaded as WGS84") for row in rows)


def test_search_log_is_multilingual_and_saturated() -> None:
    rows = read_csv("SEARCH_LOG.csv")
    languages = ";".join(row["language"] for row in rows)
    for language in ("English", "Chinese simplified", "Traditional Chinese", "Japanese", "Korean"):
        assert language in languages
    tail = rows[-2:]
    assert all(row["materially_new_high_value_family"] == "NO" for row in tail)
    assert "first consecutive" in tail[0]["disposition"]
    assert "second consecutive" in tail[1]["disposition"]


def test_coverage_matrix_has_required_geographies_and_actor_submatrices() -> None:
    rows = read_csv("SOURCE_COVERAGE_MATRIX.csv")
    required_geographies = {
        "Taiwan East",
        "Taiwan South",
        "Taiwan Strait",
        "Bashi/Luzon Strait",
        "East China Sea",
        "Senkaku/Diaoyu",
        "South China Sea",
        "Yellow Sea",
        "Western Pacific",
        "Indian Ocean",
        "Global",
    }
    assert required_geographies <= set(rows[0])
    actors = ";".join(row["actor_submatrix"] for row in rows)
    for actor in ("PLAN", "CCG", "RESEARCH", "FISHING", "MILITIA"):
        assert actor in actors
    allowed = {"", "RAW", "AGG", "DETECT", "EVENT", "REF"}
    assert all(row[g] in allowed for row in rows for g in required_geographies)


def test_vessel_crosswalk_preserves_identity_uncertainty() -> None:
    rows = read_csv("VESSEL_SOURCE_CROSSWALK.csv")
    assert len(rows) == 149 + 46
    amti = [row for row in rows if row["source_ids"] == "amti_hainan_militia"]
    assert len(amti) == 149
    assert {row["identity_confidence"] for row in amti} >= {"HIGH_CONFIDENCE", "LIKELY"}
    for row in rows:
        for field in ("mmsi_primary", "mmsi_secondary"):
            assert not row[field] or (row[field].isdigit() and len(row[field]) == 9)


def test_json_equivalents_match_csv_row_counts() -> None:
    for stem in (
        "SOURCE_SCORECARD",
        "SOURCE_COVERAGE_MATRIX",
        "SOURCE_LICENSE_MATRIX",
        "SEARCH_LOG",
        "VESSEL_SOURCE_CROSSWALK",
        "RETRIEVAL_TEST_RESULTS",
    ):
        rows = read_csv(f"{stem}.csv")
        parsed = json.loads((CENSUS / f"{stem}.json").read_text(encoding="utf-8"))
        assert len(parsed) == len(rows)


def test_census_does_not_reference_private_or_local_research_data() -> None:
    joined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CENSUS.iterdir()
        if path.suffix.lower() in {".md", ".csv", ".json"}
    ).lower()
    forbidden = (
        "sfc-cns dropbox",
        "ais_data/vessels",
        "events-mmsi-",
        ".tmp/r3-retrieval",
        "c:/users/windows",
        "c:\\users\\windows",
    )
    assert not any(value in joined for value in forbidden)
