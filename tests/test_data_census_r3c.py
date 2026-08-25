from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "docs" / "data-census"
R3C = CENSUS / "r3c-gfw"

REQUIRED = {
    "GFW_VESSEL_RESOLUTION.csv",
    "GFW_VESSEL_RESOLUTION.json",
    "GFW_TRACK_ACCESS_TESTS.csv",
    "GFW_TRACK_ACCESS_TESTS.json",
    "GFW_EVENT_ACCESS_TESTS.csv",
    "GFW_EVENT_ACCESS_TESTS.json",
    "GFW_ACTOR_COVERAGE_SUMMARY.csv",
    "GFW_TAIWAN_EAST_ASIA_COVERAGE.csv",
    "DEEP_SEA_MINING_WATCH_AUDIT.md",
    "GFW_LICENSE_ACCESS_MATRIX.csv",
    "R3_CENSUS_CORRECTIONS.md",
    "R3C_CONNECTOR_RECOMMENDATION.md",
}

ACCESS_CLASSES = {
    "OPEN_DOWNLOAD",
    "OPEN_API",
    "OPEN_BULK_ARCHIVE",
    "OPEN_INTERACTIVE_VIEW",
    "OPEN_INTERACTIVE_EXPORT",
    "ACCOUNT_REQUIRED",
    "REQUEST_REQUIRED",
    "ACADEMIC_ACCESS",
    "PARTNER_ONLY",
    "COMMERCIAL",
    "BYO_LICENSED",
    "REFERENCE_ONLY",
}

RETRIEVAL_STATUSES = {
    "NOT_TESTED",
    "NO_IDENTITY_MATCH",
    "IDENTITY_MATCH_NO_TRACK",
    "TRACK_VISIBLE_NOT_EXPORTABLE",
    "EXPORT_DOCUMENTED_AUTH_REQUIRED",
    "EXPORT_TESTED_SUCCESS",
    "API_TESTED_SUCCESS",
    "BULK_ONLY_NO_INDIVIDUAL_TRACK",
    "COMMERCIAL_ONLY",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_required_r3c_artifacts_exist() -> None:
    assert R3C.is_dir()
    assert REQUIRED <= {path.name for path in R3C.iterdir()}


def test_csv_json_pairs_have_identical_rows() -> None:
    for stem in ("GFW_VESSEL_RESOLUTION", "GFW_TRACK_ACCESS_TESTS", "GFW_EVENT_ACCESS_TESTS"):
        csv_rows = read_csv(R3C / f"{stem}.csv")
        json_rows = json.loads((R3C / f"{stem}.json").read_text(encoding="utf-8"))
        assert csv_rows == json_rows


def test_all_195_entities_receive_bounded_resolution_status() -> None:
    crosswalk = read_csv(CENSUS / "VESSEL_SOURCE_CROSSWALK.csv")
    resolution = read_csv(R3C / "GFW_VESSEL_RESOLUTION.csv")
    assert len(crosswalk) == len(resolution) == 195
    assert len({row["vessel_key"] for row in crosswalk}) == 195
    assert {row["vessel_key"] for row in crosswalk} == {
        row["mgrb_entity_id"] for row in resolution
    }
    assert all(row["attempted"] == "YES" for row in resolution)
    assert all(row["resolution_status"] in RETRIEVAL_STATUSES for row in resolution)
    assert Counter(row["resolution_status"] for row in resolution) == {
        "IDENTITY_MATCH_NO_TRACK": 17,
        "NO_IDENTITY_MATCH": 136,
        "NOT_TESTED": 42,
    }
    assert sum(row["successfully_searched"] == "YES" for row in resolution) == 153


def test_match_status_does_not_hide_authentication_block() -> None:
    rows = read_csv(R3C / "GFW_VESSEL_RESOLUTION.csv")
    blocked = [row for row in rows if row["resolution_status"] == "NOT_TESTED"]
    archive_no_match = [row for row in rows if row["resolution_status"] == "NO_IDENTITY_MATCH"]
    assert len(blocked) == 42
    assert all(row["successfully_searched"] == "NO" for row in blocked)
    assert all(row["online_api_status"] == "AUTH_BLOCKED_HTTP_401" for row in blocked)
    assert all(row["successfully_searched"] == "YES" for row in archive_no_match)
    assert all("not a global GFW no-match" in row["discrepancy_notes"] for row in archive_no_match)


def test_exact_matches_are_unique_and_ambiguity_is_preserved() -> None:
    rows = read_csv(R3C / "GFW_VESSEL_RESOLUTION.csv")
    exact = [row for row in rows if row["match_status"] == "EXACT_IDENTIFIER"]
    assert len(exact) == 17
    keys = [row["gfw_identity_key"] for row in exact]
    assert all(key.startswith("mmsi:") for key in keys)
    assert len(keys) == len(set(keys))
    for row in rows:
        if int(row["candidate_count"]) > 1:
            assert row["match_status"] == "AMBIGUOUS"
    assert not any(row["match_status"] == "NAME_ONLY_PROBABLE" for row in rows)
    assert all(
        row["identifier_snowball_status"] == "CHECKED_NO_MATERIALLY_NEW_SOURCE_LINK"
        for row in exact
    )
    assert all(row["existing_census_source_ids"] == "amti_hainan_militia" for row in exact)


def test_actor_type_and_counts_are_preserved() -> None:
    crosswalk = read_csv(CENSUS / "VESSEL_SOURCE_CROSSWALK.csv")
    resolution = read_csv(R3C / "GFW_VESSEL_RESOLUTION.csv")
    expected_actor = {
        row["vessel_key"]: (
            "MARITIME_MILITIA"
            if row["actor_family"] == "MILITIA;FISHING"
            else ("RESEARCH_SURVEY" if row["actor_family"] == "RESEARCH" else row["actor_family"])
        )
        for row in crosswalk
    }
    assert all(expected_actor[row["mgrb_entity_id"]] == row["actor_type"] for row in resolution)
    summary = {row["actor_type"]: row for row in read_csv(R3C / "GFW_ACTOR_COVERAGE_SUMMARY.csv")}
    assert set(summary) == {"PLAN", "CCG", "RESEARCH_SURVEY", "FISHING", "MARITIME_MILITIA", "OTHER"}
    assert {actor: int(row["crosswalk_entities"]) for actor, row in summary.items()} == {
        "PLAN": 4,
        "CCG": 29,
        "RESEARCH_SURVEY": 13,
        "FISHING": 0,
        "MARITIME_MILITIA": 149,
        "OTHER": 0,
    }
    assert int(summary["MARITIME_MILITIA"]["exact_identifier_matches"]) == 17
    assert all(int(summary[actor]["exact_identifier_matches"]) == 0 for actor in ("PLAN", "CCG", "RESEARCH_SURVEY"))


def test_interface_access_classes_and_terms_are_not_flattened() -> None:
    rows = read_csv(R3C / "GFW_LICENSE_ACCESS_MATRIX.csv")
    ids = {row["interface_id"] for row in rows}
    assert len(ids) == len(rows)
    assert {row["access_class"] for row in rows} <= ACCESS_CLASSES
    assert {
        "gfw_vessel_search_ui",
        "gfw_vessel_search_api",
        "gfw_individual_track_ui",
        "gfw_individual_track_export",
        "gfw_vessel_events_api",
        "gfw_global_presence_api",
        "gfw_bulk_fishing_identity",
        "gfw_bulk_fleet_monthly",
        "gfw_sar_api",
        "gfw_viirs_related",
        "dsm_watch_public_portal",
        "dsm_watch_vessel_event_access",
    } <= ids
    by_id = {row["interface_id"]: row for row in rows}
    assert by_id["gfw_bulk_fishing_identity"]["access_class"] == "OPEN_BULK_ARCHIVE"
    assert by_id["gfw_vessel_search_api"]["access_class"] == "ACCOUNT_REQUIRED"
    assert by_id["gfw_individual_track_export"]["access_class"] == "ACCOUNT_REQUIRED"
    assert by_id["dsm_watch_public_portal"]["access_class"] == "OPEN_INTERACTIVE_VIEW"
    assert by_id["dsm_watch_vessel_event_access"]["access_class"] == "ACCOUNT_REQUIRED"


def test_track_and_event_statuses_make_no_unsupported_claim() -> None:
    tracks = read_csv(R3C / "GFW_TRACK_ACCESS_TESTS.csv")
    events = read_csv(R3C / "GFW_EVENT_ACCESS_TESTS.csv")
    matched_ids = {
        row["mgrb_entity_id"]
        for row in read_csv(R3C / "GFW_VESSEL_RESOLUTION.csv")
        if row["match_status"] == "EXACT_IDENTIFIER"
    }
    assert len(matched_ids) == 17
    assert {row["mgrb_entity_id"] for row in tracks} == matched_ids
    assert {row["mgrb_entity_id"] for row in events} == matched_ids
    assert len(tracks) == 17 * 4
    assert len(events) == 17 * 5
    assert {row["retrieval_status"] for row in tracks} <= RETRIEVAL_STATUSES
    assert {row["retrieval_status"] for row in events} <= RETRIEVAL_STATUSES
    assert sum(int(row["position_count"]) for row in tracks) == 0
    assert not any(row["actual_download_success"] == "YES" and int(row["position_count"]) for row in tracks)
    for row in tracks:
        if row["track_export_available"] == "YES":
            assert row["retrieval_status"] in {
                "EXPORT_DOCUMENTED_AUTH_REQUIRED",
                "EXPORT_TESTED_SUCCESS",
            }
        if row["retrieval_status"] == "EXPORT_DOCUMENTED_AUTH_REQUIRED":
            assert row["actual_download_success"] == "NO"
    assert {row["event_type"] for row in events} == {
        "fishing",
        "encounter",
        "loitering",
        "port_visit",
        "AIS_gap",
    }
    assert all(row["event_count"] == "" for row in events)
    assert all("not intentional disabling" in row["methodological_caveat"] for row in events)


def test_stratified_sample_and_taiwan_metrics_are_honest() -> None:
    tracks = read_csv(R3C / "GFW_TRACK_ACCESS_TESTS.csv")
    bulk_tests = [row for row in tracks if row["interface"] == "BULK_ARCHIVE"]
    assert len(bulk_tests) == 17
    assert sum(row["actor_type"] == "MARITIME_MILITIA" for row in bulk_tests) >= 10
    taiwan = read_csv(R3C / "GFW_TAIWAN_EAST_ASIA_COVERAGE.csv")
    assert len(taiwan) == 17
    assert all(row["individual_positions_usable"] == "NO" for row in taiwan)
    assert sum(int(row["retrieved_position_count"]) for row in taiwan) == 0
    assert all(row["geographic_intersection_confirmed"] == "NO" for row in taiwan)
    recent_summary = [
        row
        for row in taiwan
        if any(2022 <= int(year) <= 2026 for year in row["available_bulk_summary_years"].split(";"))
    ]
    assert len(recent_summary) == 16


def test_updated_census_referential_integrity_and_interface_rows() -> None:
    score = read_csv(CENSUS / "SOURCE_SCORECARD.csv")
    coverage = read_csv(CENSUS / "SOURCE_COVERAGE_MATRIX.csv")
    licenses = read_csv(CENSUS / "SOURCE_LICENSE_MATRIX.csv")
    retrieval = read_csv(CENSUS / "RETRIEVAL_TEST_RESULTS.csv")
    score_ids = {row["source_id"] for row in score}
    required_interface_rows = {
        "gfw_vessel_search_ui",
        "gfw_vessel_search_api",
        "gfw_individual_track_ui",
        "gfw_individual_track_export",
        "gfw_viirs_related",
        "dsm_watch_vessel_event_access",
    }
    assert required_interface_rows <= score_ids
    assert required_interface_rows <= {row["source_id"] for row in coverage}
    assert required_interface_rows <= {row["source_id"] for row in licenses}
    dsm = next(row for row in score if row["source_id"] == "dsm_watch")
    assert dsm["access_class"] == "OPEN_INTERACTIVE_VIEW"
    assert dsm["connector_priority"] == "P2"
    assert {row["source_id"] for row in retrieval} <= score_ids
    crosswalk = read_csv(CENSUS / "VESSEL_SOURCE_CROSSWALK.csv")
    referenced = {source for row in crosswalk for source in row["source_ids"].split(";") if source}
    assert referenced <= score_ids
    assert sum(row["track_availability"].startswith("GFW bulk identity/activity match") for row in crosswalk) == 17


def test_no_private_or_licensed_track_data_entered_r3c() -> None:
    joined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in R3C.iterdir()
        if path.suffix.lower() in {".md", ".csv", ".json"}
    ).lower()
    forbidden = (
        "sfc-cns dropbox",
        "events-mmsi-",
        "ais_data/vessels",
        "c:/users/windows",
        "c:\\users\\windows",
        ".tmp/r3-retrieval",
    )
    assert not any(value in joined for value in forbidden)


def test_markdown_records_partial_authentication_state() -> None:
    corrections = (R3C / "R3_CENSUS_CORRECTIONS.md").read_text(encoding="utf-8")
    dsm = (R3C / "DEEP_SEA_MINING_WATCH_AUDIT.md").read_text(encoding="utf-8")
    recommendation = (R3C / "R3C_CONNECTOR_RECOMMENDATION.md").read_text(encoding="utf-8")
    assert "PARTIAL_R3C_BLOCKED_BY_GFW_AUTHENTICATION" in corrections
    assert "195 entities" in corrections
    assert "Actual individual position records retrieved: **0**" in corrections
    assert "REFERENCE_ONLY" in dsm
    assert "OPEN_INTERACTIVE_VIEW" in dsm and "ACCOUNT_REQUIRED" in dsm
    assert "No production connector is implemented" in recommendation
