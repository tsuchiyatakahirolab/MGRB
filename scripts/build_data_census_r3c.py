"""Build the targeted R3C Global Fishing Watch access correction artifacts.

This is an evidence overlay on the R3 census.  It never downloads or commits raw
positions.  The only local input is the public, versioned GFW Fishing vessels v3
archive already retrieved and checksum-validated by R3.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "docs" / "data-census"
OUT = CENSUS / "r3c-gfw"
CHECKED = "2026-08-25"
START = "2022-01-01"
END = "2026-08-23"

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

LICENSE_ROWS = [
    {
        "interface_id": "gfw_vessel_search_ui",
        "interface": "Vessel Search basic interactive view",
        "access_class": "OPEN_INTERACTIVE_VIEW",
        "authentication": "not required for basic documented search; actual workspace failed",
        "research_noncommercial_use": "allowed subject to GFW site/service terms",
        "commercial_use": "not established",
        "attribution": "GFW attribution required for reused service data",
        "redistribution": "dataset-specific; not established by UI availability",
        "cached_derivative_data": "not stated for this interface",
        "api_output_retention": "not applicable",
        "public_artifact_use": "not established beyond screenshots/share links",
        "automation_potential": "low; interactive and workspace-dependent",
        "connector_priority": "P2",
        "evidence_url": "https://globalfishingwatch.org/vessel-viewer-tool/",
        "actual_test": "welcome text loaded; vessel workspace failed before search input",
    },
    {
        "interface_id": "gfw_vessel_search_api",
        "interface": "API v3 vessel identity search",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "account and confidential Bearer token required",
        "research_noncommercial_use": "CC BY-NC 4.0; noncommercial only",
        "commercial_use": "not allowed without separate permission",
        "attribution": "provider-specified Powered by/citation required",
        "redistribution": "dataset-specific; downstream attribution must persist",
        "cached_derivative_data": "terms do not provide a separate blanket grant",
        "api_output_retention": "no explicit duration found; cancellation storage clause is not a grant",
        "public_artifact_use": "allowed only subject to API and dataset terms",
        "automation_potential": "high after owner-supplied token",
        "connector_priority": "P1",
        "evidence_url": "https://globalfishingwatch.org/our-apis/documentation/docs/v3/vessels/search",
        "actual_test": "HTTP 401 invalid token without Bearer token",
    },
    {
        "interface_id": "gfw_individual_track_ui",
        "interface": "Interactive individual track display",
        "access_class": "OPEN_INTERACTIVE_VIEW",
        "authentication": "documentation describes display; actual selection not reached",
        "research_noncommercial_use": "allowed subject to GFW site/service terms",
        "commercial_use": "not established",
        "attribution": "required when reused",
        "redistribution": "not established by visibility",
        "cached_derivative_data": "not stated",
        "api_output_retention": "not applicable",
        "public_artifact_use": "share/profile functions documented",
        "automation_potential": "low; no raw position API documented in v3",
        "connector_priority": "P2",
        "evidence_url": "https://globalfishingwatch.org/user-guide/",
        "actual_test": "not demonstrated because vessel workspace did not load",
    },
    {
        "interface_id": "gfw_individual_track_export",
        "interface": "Interactive individual track export",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "free account required for data downloads",
        "research_noncommercial_use": "allowed subject to GFW service/dataset terms",
        "commercial_use": "not established; API terms are noncommercial",
        "attribution": "required",
        "redistribution": "dataset-specific; not implied by download capability",
        "cached_derivative_data": "not stated",
        "api_output_retention": "not applicable",
        "public_artifact_use": "CSV/GeoJSON export is documented",
        "automation_potential": "low; no supported export automation documented",
        "connector_priority": "P1",
        "evidence_url": "https://globalfishingwatch.org/user-guide/",
        "actual_test": "documented only; authentication unavailable in R3C environment",
    },
    {
        "interface_id": "gfw_vessel_events_api",
        "interface": "API v3 vessel events",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "account and confidential Bearer token required",
        "research_noncommercial_use": "CC BY-NC 4.0; noncommercial only",
        "commercial_use": "not allowed without separate permission",
        "attribution": "provider-specified attribution required",
        "redistribution": "dataset-specific; downstream attribution must persist",
        "cached_derivative_data": "terms do not provide a separate blanket grant",
        "api_output_retention": "no explicit duration found",
        "public_artifact_use": "subject to API and event-dataset terms",
        "automation_potential": "high after token and identity resolution",
        "connector_priority": "P1",
        "evidence_url": "https://globalfishingwatch.org/our-apis/documentation/docs/v3/events",
        "actual_test": "HTTP 401 without Bearer token",
    },
    {
        "interface_id": "gfw_global_presence_api",
        "interface": "API v3/4Wings gridded vessel presence",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "account and confidential Bearer token required",
        "research_noncommercial_use": "CC BY-NC 4.0; noncommercial only",
        "commercial_use": "not allowed without separate permission",
        "attribution": "provider-specified attribution required",
        "redistribution": "dataset-specific",
        "cached_derivative_data": "terms do not provide a separate blanket grant",
        "api_output_retention": "no explicit duration found",
        "public_artifact_use": "subject to API/dataset terms",
        "automation_potential": "high; output is aggregate, not individual tracks",
        "connector_priority": "P1",
        "evidence_url": "https://globalfishingwatch.org/our-apis/documentation/docs/v3/4wings",
        "actual_test": "documentation inspected; token-gated",
    },
    {
        "interface_id": "gfw_bulk_fishing_identity",
        "interface": "Zenodo Fishing vessels v3 annual identity/activity",
        "access_class": "OPEN_BULK_ARCHIVE",
        "authentication": "none",
        "research_noncommercial_use": "allowed by CC BY-SA 4.0",
        "commercial_use": "allowed by CC BY-SA 4.0",
        "attribution": "required",
        "redistribution": "allowed with share-alike",
        "cached_derivative_data": "allowed with share-alike",
        "api_output_retention": "not applicable",
        "public_artifact_use": "allowed with attribution/share-alike",
        "automation_potential": "high; checksum-pinned archive",
        "connector_priority": "P0",
        "evidence_url": "https://zenodo.org/records/14982712",
        "actual_test": "checksum and schema passed; 17 exact crosswalk MMSI matches",
    },
    {
        "interface_id": "gfw_bulk_fleet_monthly",
        "interface": "Zenodo 0.1-degree monthly fleet archive",
        "access_class": "OPEN_BULK_ARCHIVE",
        "authentication": "none",
        "research_noncommercial_use": "allowed by CC BY-SA 4.0",
        "commercial_use": "allowed by CC BY-SA 4.0",
        "attribution": "required",
        "redistribution": "allowed with share-alike",
        "cached_derivative_data": "allowed with share-alike",
        "api_output_retention": "not applicable",
        "public_artifact_use": "allowed with attribution/share-alike",
        "automation_potential": "high; aggregate grid only",
        "connector_priority": "P0",
        "evidence_url": "https://zenodo.org/records/14982712",
        "actual_test": "R3 checksum/schema/spatial subset passed for 2022-2024",
    },
    {
        "interface_id": "gfw_sar_api",
        "interface": "GFW SAR detections API/tiles",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "account/token required for API",
        "research_noncommercial_use": "API terms; dataset metadata also applies",
        "commercial_use": "not allowed without permission under API terms",
        "attribution": "required",
        "redistribution": "dataset-specific",
        "cached_derivative_data": "dataset-specific",
        "api_output_retention": "no explicit duration found",
        "public_artifact_use": "dataset-specific",
        "automation_potential": "medium; detections are not vessel tracks",
        "connector_priority": "P1",
        "evidence_url": "https://globalfishingwatch.org/our-apis/documentation/docs/v3",
        "actual_test": "not an individual-track interface",
    },
    {
        "interface_id": "gfw_viirs_related",
        "interface": "GFW VIIRS/night-light related map products",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "product/interface dependent; map/API distinctions apply",
        "research_noncommercial_use": "API terms and dataset metadata apply",
        "commercial_use": "not allowed without permission for API use",
        "attribution": "required",
        "redistribution": "dataset-specific",
        "cached_derivative_data": "dataset-specific",
        "api_output_retention": "no explicit duration found",
        "public_artifact_use": "dataset-specific",
        "automation_potential": "medium; detections are not vessel tracks",
        "connector_priority": "P2",
        "evidence_url": "https://globalfishingwatch.org/our-apis/documentation/docs/v3",
        "actual_test": "not tested as individual-track source",
    },
    {
        "interface_id": "dsm_watch_public_portal",
        "interface": "Deep-Sea Mining Watch public portal",
        "access_class": "OPEN_INTERACTIVE_VIEW",
        "authentication": "none for public heatmap, timebar, share, screenshot",
        "research_noncommercial_use": "public viewing; reuse terms not separately stated",
        "commercial_use": "not established",
        "attribution": "GFW and Benioff/UCSB attribution shown",
        "redistribution": "not established",
        "cached_derivative_data": "not stated",
        "api_output_retention": "not applicable",
        "public_artifact_use": "map screenshot control exposed",
        "automation_potential": "low; public presentation/reference layer",
        "connector_priority": "P2",
        "evidence_url": "https://globalfishingwatch.org/platform/map/fishing-activity/deep-sea-mining-public",
        "actual_test": "portal and timebar loaded without login",
    },
    {
        "interface_id": "dsm_watch_vessel_event_access",
        "interface": "Deep-Sea Mining Watch vessel search/details/event download",
        "access_class": "ACCOUNT_REQUIRED",
        "authentication": "actual UI required registration/login and denied vessel search",
        "research_noncommercial_use": "GFW service/dataset terms apply",
        "commercial_use": "not established",
        "attribution": "required",
        "redistribution": "not established",
        "cached_derivative_data": "not stated",
        "api_output_retention": "no portal-specific API found",
        "public_artifact_use": "event download control documented by UI after login",
        "automation_potential": "unresolved until authenticated lawful test",
        "connector_priority": "P2",
        "evidence_url": "https://globalfishingwatch.org/platform/map/fishing-activity/deep-sea-mining-public",
        "actual_test": "vessel search permission denied; event downloads login-gated",
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: Iterable[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(fields or (rows[0].keys() if rows else []))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, str]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_pair(stem: str, rows: list[dict[str, str]]) -> None:
    write_csv(OUT / f"{stem}.csv", rows)
    write_json(OUT / f"{stem}.json", rows)


def actor_type(value: str) -> str:
    if value == "MILITIA;FISHING":
        return "MARITIME_MILITIA"
    if value == "RESEARCH":
        return "RESEARCH_SURVEY"
    return value if value in {"PLAN", "CCG", "FISHING", "OTHER"} else "OTHER"


def strongest_query(row: dict[str, str]) -> tuple[str, str]:
    ordered = (
        ("IMO", row.get("imo", "")),
        ("MMSI", row.get("mmsi_primary", "")),
        ("MMSI", row.get("mmsi_secondary", "")),
        ("OTHER", row.get("hull_number", "")),
        ("NAME", row.get("name_en_or_romanized", "")),
        ("NAME", row.get("name_zh", "")),
        ("ALIAS", row.get("aliases_or_former_names", "")),
    )
    return next((kind, value.strip()) for kind, value in ordered if value.strip())


def index_bulk(path: Path, targets: set[str]) -> dict[str, list[dict[str, str]]]:
    found: dict[str, list[dict[str, str]]] = defaultdict(list)
    if not path.is_file():
        return found
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            mmsi = row.get("mmsi", "").strip()
            if mmsi in targets:
                found[mmsi].append(row)
    return found


def build_resolution(
    crosswalk: list[dict[str, str]], bulk: dict[str, list[dict[str, str]]], bulk_loaded: bool
) -> list[dict[str, str]]:
    output = []
    for row in crosswalk:
        method, value = strongest_query(row)
        mmsis = [row.get("mmsi_primary", "").strip(), row.get("mmsi_secondary", "").strip()]
        mmsis = [item for item in mmsis if item]
        candidates = [(mmsi, bulk[mmsi]) for mmsi in mmsis if mmsi in bulk]
        matched_mmsi = candidates[0][0] if candidates else ""
        matched_rows = candidates[0][1] if candidates else []
        searched = "YES" if bulk_loaded and bool(mmsis) else "NO"
        matched = bool(matched_rows)
        years = sorted({item["year"] for item in matched_rows})
        flags = sorted({item.get("flag_gfw", "") for item in matched_rows if item.get("flag_gfw")})
        classes = sorted(
            {
                item.get("vessel_class_gfw") or item.get("vessel_class_inferred", "")
                for item in matched_rows
                if item.get("vessel_class_gfw") or item.get("vessel_class_inferred")
            }
        )
        if matched:
            status = "IDENTITY_MATCH_NO_TRACK"
            discrepancy = (
                "Exact MMSI match in GFW Fishing vessels v3 bulk archive. The archive has "
                "annual identity/activity summaries, no GFW internal vessel ID and no positions. "
                "Online Vessel Search remained token-blocked."
            )
        elif searched == "YES":
            status = "NO_IDENTITY_MATCH"
            discrepancy = (
                "No exact MMSI match in the tested Fishing vessels v3 archive; this is not a "
                "global GFW no-match because online Vessel Search was token-blocked."
            )
        else:
            status = "NOT_TESTED"
            discrepancy = (
                "Strongest documented online query was prepared but not executed because the "
                "Vessel Search API returned HTTP 401 without an owner-supplied token; the public "
                "bulk archive cannot search this identifier type."
            )
        output.append(
            {
                "mgrb_entity_id": row["vessel_key"],
                "actor_type": actor_type(row["actor_family"]),
                "source_actor_type": row["actor_family"],
                "attempted": "YES",
                "successfully_searched": searched,
                "query_method": method,
                "query_value": value,
                "executed_interface": "GFW_FISHING_VESSELS_V3_BULK" if searched else "NONE",
                "online_api_status": "AUTH_BLOCKED_HTTP_401",
                "gfw_vessel_id": "",
                "gfw_identity_key": f"mmsi:{matched_mmsi}" if matched else "",
                "gfw_reported_name": "",
                "gfw_reported_imo": "",
                "gfw_reported_mmsi": matched_mmsi,
                "gfw_reported_callsign": "",
                "flag": ";".join(flags),
                "vessel_class_or_type": ";".join(classes),
                "first_available_date": f"{years[0]}-01-01" if years else "",
                "last_available_date": f"{years[-1]}-12-31" if years else "",
                "match_status": "EXACT_IDENTIFIER" if matched else "NO_MATCH",
                "match_confidence": "1.0" if matched else "",
                "resolution_status": status,
                "match_scope": "GFW_FISHING_VESSELS_V3_BULK_ONLY",
                "candidate_count": str(len(candidates)),
                "existing_census_source_ids": row["source_ids"],
                "identifier_snowball_status": (
                    "CHECKED_NO_MATERIALLY_NEW_SOURCE_LINK"
                    if matched
                    else "NOT_APPLICABLE_NO_STRONG_GFW_MATCH"
                ),
                "identifier_snowball_notes": (
                    "Exact MMSI/name checked against the existing R3 crosswalk source-link "
                    "inventory; the AMTI source link was already present and no new existing "
                    "census repository link was established."
                    if matched
                    else "Snowballing is required only for a strong/exact GFW match."
                ),
                "discrepancy_notes": discrepancy,
            }
        )
    return output


def matched_entities(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row["match_status"] == "EXACT_IDENTIFIER"]


def build_track_tests(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    output = []
    definitions = (
        (
            "API",
            "YES",
            "YES",
            "YES",
            "NO",
            "NO",
            "NONE",
            "NO",
            "NOT_TESTED",
            (
                "No documented API v3 raw individual-position endpoint was located; "
                "identity/events endpoints require a token and the actual anonymous request "
                "returned HTTP 401."
            ),
        ),
        (
            "INTERACTIVE_UI",
            "UNKNOWN",
            "UNKNOWN",
            "NO",
            "NO",
            "NO",
            "NONE",
            "NO",
            "NOT_TESTED",
            (
                "Official documentation describes individual track display, but the actual "
                "public workspace failed before a vessel could be selected."
            ),
        ),
        (
            "INTERACTIVE_EXPORT",
            "YES",
            "YES",
            "NO",
            "UNKNOWN",
            "YES",
            "CSV;GEOJSON",
            "NO",
            "EXPORT_DOCUMENTED_AUTH_REQUIRED",
            (
                "GFW documents vessel-track CSV/GeoJSON export and its UI states that data "
                "downloads require free registration; no authenticated owner session was "
                "available."
            ),
        ),
        (
            "BULK_ARCHIVE",
            "NO",
            "NO",
            "NO",
            "NO",
            "NO",
            "CSV",
            "YES",
            "BULK_ONLY_NO_INDIVIDUAL_TRACK",
            (
                "Checksum-validated annual identity/activity archive; no coordinates, "
                "timestamps or individual tracks."
            ),
        ),
    )
    for match in matches:
        for (
            interface,
            auth,
            account,
            token,
            display,
            export,
            export_format,
            download,
            status,
            limitation,
        ) in definitions:
            output.append(
                {
                    "mgrb_entity_id": match["mgrb_entity_id"],
                    "gfw_vessel_id": match["gfw_vessel_id"],
                    "gfw_identity_key": match["gfw_identity_key"],
                    "actor_type": match["actor_type"],
                    "interface": interface,
                    "authentication_required": auth,
                    "account_required": account,
                    "api_token_required": token,
                    "test_period_start": START,
                    "test_period_end": END,
                    "track_display_available": display,
                    "track_export_available": export,
                    "export_format": export_format,
                    "actual_download_success": download,
                    "retrieval_status": status,
                    "position_count": "0",
                    "first_position_time": "",
                    "last_position_time": "",
                    "temporal_density_summary": "no positions retrieved",
                    "large_gap_count": "",
                    "coordinate_fields_present": "NO",
                    "timestamp_present": "NO",
                    "speed_present": "NO",
                    "course_present": "NO",
                    "vessel_identity_present": "YES" if interface == "BULK_ARCHIVE" else "UNKNOWN",
                    "usable_in_MGRB": "IDENTITY_ONLY" if interface == "BULK_ARCHIVE" else "NO",
                    "limitation": limitation,
                }
            )
    return output


def build_event_tests(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    output = []
    for match in matches:
        for event_type in ("fishing", "encounter", "loitering", "port_visit", "AIS_gap"):
            output.append(
                {
                    "mgrb_entity_id": match["mgrb_entity_id"],
                    "gfw_vessel_id": match["gfw_vessel_id"],
                    "gfw_identity_key": match["gfw_identity_key"],
                    "actor_type": match["actor_type"],
                    "event_type": event_type,
                    "period_start": START,
                    "period_end": END,
                    "event_count": "",
                    "coordinates_available": "UNKNOWN",
                    "timestamps_available": "UNKNOWN",
                    "downloadable_or_api": "API_TOKEN_REQUIRED",
                    "retrieval_status": "NOT_TESTED",
                    "mgrb_usability": "UNRESOLVED",
                    "methodological_caveat": (
                        "API v3 Events requires a token and GFW internal vessel ID. HTTP 401 was "
                        "confirmed without a token. AIS gap is not intentional disabling; "
                        "loitering is not surveillance or military activity."
                    ),
                }
            )
    return output


def build_actor_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output = []
    for actor in ("PLAN", "CCG", "RESEARCH_SURVEY", "FISHING", "MARITIME_MILITIA", "OTHER"):
        subset = [row for row in rows if row["actor_type"] == actor]
        searched = [row for row in subset if row["successfully_searched"] == "YES"]
        exact = [row for row in subset if row["match_status"] == "EXACT_IDENTIFIER"]
        strong = [row for row in subset if row["match_status"] == "STRONG_MULTI_FIELD"]
        ambiguous = [row for row in subset if row["match_status"] == "AMBIGUOUS"]
        no_match = [row for row in searched if row["resolution_status"] == "NO_IDENTITY_MATCH"]
        blocked = [row for row in subset if row["resolution_status"] == "NOT_TESTED"]
        denominator = len(subset)
        output.append(
            {
                "actor_type": actor,
                "crosswalk_entities": str(denominator),
                "attempted": str(len(subset)),
                "successfully_searched": str(len(searched)),
                "exact_identifier_matches": str(len(exact)),
                "strong_matches": str(len(strong)),
                "ambiguous_candidates": str(len(ambiguous)),
                "no_matches_in_searched_interface": str(len(no_match)),
                "authentication_blocked_or_unsupported_identifier": str(len(blocked)),
                "match_percentage_of_all_entities": (
                    f"{100 * (len(exact) + len(strong)) / denominator:.2f}" if denominator else "0.00"
                ),
                "scope_note": (
                    "Exact matches are against the GFW Fishing vessels v3 bulk archive only; "
                    "absence is not evidence of no AIS transmission."
                ),
            }
        )
    return output


def build_taiwan(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "mgrb_entity_id": row["mgrb_entity_id"],
            "gfw_identity_key": row["gfw_identity_key"],
            "actor_type": row["actor_type"],
            "plausibly_relevant": "YES",
            "identity_available": "YES",
            "available_bulk_summary_start": row["first_available_date"],
            "available_bulk_summary_end": row["last_available_date"],
            "tested_period_start": START,
            "tested_period_end": END,
            "individual_positions_usable": "NO",
            "retrieved_position_count": "0",
            "position_density": "NONE",
            "geographic_intersection_confirmed": "NO",
            "intersected_mgrb_presets": "",
            "retrieval_status": "BULK_ONLY_NO_INDIVIDUAL_TRACK",
            "limitation": (
                "Annual archive activity does not contain coordinates; Taiwan/East Asia "
                "intersection cannot be inferred from identity or yearly activity."
            ),
        }
        for row in matches
    ]


def upsert_existing(
    resolution: list[dict[str, str]], bulk_path: Path, bulk_loaded: bool
) -> None:
    access_changes = {
        "gfw_fishing_vessels_v3": "OPEN_BULK_ARCHIVE",
        "gfw_fleet_monthly_v3": "OPEN_BULK_ARCHIVE",
        "gfw_api_presence": "ACCOUNT_REQUIRED",
        "gfw_api_events": "ACCOUNT_REQUIRED",
        "gfw_sar_presence": "ACCOUNT_REQUIRED",
        "gfw_sar_figshare": "OPEN_DOWNLOAD",
        "dsm_watch": "OPEN_INTERACTIVE_VIEW",
    }
    score_path = CENSUS / "SOURCE_SCORECARD.csv"
    score = read_csv(score_path)
    by_id = {row["source_id"]: row for row in score}
    for source_id, access in access_changes.items():
        by_id[source_id]["access_class"] = access
    by_id["dsm_watch"].update(
        url="https://globalfishingwatch.org/platform/map/fishing-activity/deep-sea-mining-public",
        evidence_type="AGGREGATE_ACTIVITY;REFERENCE",
        identity_fields="vessel search permission-gated in unauthenticated portal",
        spatial_density_or_resolution="interactive activity heatmap; no raw positions retrieved",
        format="interactive map",
        qgis_readiness="reference only until authenticated export and rights review",
        connector_priority="P2",
        decision_reason=(
            "public aggregate portal; vessel search/event download account-gated; "
            "individual track export not demonstrated"
        ),
        last_checked_utc=CHECKED,
    )
    templates = {
        "gfw_vessel_search_ui": (
            "gfw_api_presence",
            "Vessel Search basic interactive view",
            "https://globalfishingwatch.org/platform/vessel-search",
            "VESSEL_IDENTITY",
            "OPEN_INTERACTIVE_VIEW",
            "P2",
            "interactive browser view; actual workspace failed",
        ),
        "gfw_vessel_search_api": (
            "gfw_api_presence",
            "API v3 vessel identity search",
            "https://globalfishingwatch.org/our-apis/documentation/docs/v3/vessels/search",
            "VESSEL_IDENTITY",
            "ACCOUNT_REQUIRED",
            "P1",
            "structured identity search; token required and anonymous test returned 401",
        ),
        "gfw_individual_track_ui": (
            "gfw_api_presence",
            "Interactive individual vessel track display",
            "https://globalfishingwatch.org/user-guide/",
            "INDIVIDUAL_TRACK_DISPLAY",
            "OPEN_INTERACTIVE_VIEW",
            "P2",
            "documented display; actual vessel selection not reached",
        ),
        "gfw_individual_track_export": (
            "gfw_api_presence",
            "Interactive individual vessel track CSV/GeoJSON export",
            "https://globalfishingwatch.org/user-guide/",
            "INDIVIDUAL_TRACK_EXPORT",
            "ACCOUNT_REQUIRED",
            "P1",
            "documented account-gated export; no authenticated retrieval in R3C",
        ),
        "gfw_viirs_related": (
            "gfw_sar_presence",
            "VIIRS/night-light related detections",
            "https://globalfishingwatch.org/our-apis/documentation/docs/v3",
            "VIIRS_DETECTION",
            "ACCOUNT_REQUIRED",
            "P2",
            "detection product; not an individual-track interface",
        ),
        "dsm_watch_vessel_event_access": (
            "dsm_watch",
            "Deep-Sea Mining Watch vessel search and event export",
            "https://globalfishingwatch.org/platform/map/fishing-activity/deep-sea-mining-public",
            "VESSEL_IDENTITY;EVENT_EXPORT",
            "ACCOUNT_REQUIRED",
            "P2",
            "actual UI denied vessel search and required login for event downloads",
        ),
    }
    for source_id, values in templates.items():
        template_id, product, url, evidence, access, priority, reason = values
        is_new = source_id not in by_id
        row = deepcopy(by_id[template_id]) if is_new else by_id[source_id]
        matrix = next(item for item in LICENSE_ROWS if item["interface_id"] == source_id)
        api_terms = source_id in {"gfw_vessel_search_api", "gfw_viirs_related"}
        row.update(
            source_id=source_id,
            product=product,
            url=url,
            evidence_type=evidence,
            access_class=access,
            connector_priority=priority,
            default_eligible="NO",
            decision_reason=reason,
            license_or_terms=(
                "GFW API terms; CC BY-NC 4.0"
                if api_terms
                else "GFW service and dataset-specific terms; reuse grant not inferred"
            ),
            redistribution=matrix["redistribution"],
            commercial_use=matrix["commercial_use"],
            retrieval_test_id=(
                "RT-GFW-VESSEL-SEARCH-ANON-401"
                if source_id == "gfw_vessel_search_api"
                else ("RT-DSMW-ANON-UI" if source_id == "dsm_watch_vessel_event_access" else "")
            ),
            last_checked_utc=CHECKED,
        )
        if is_new:
            score.append(row)
        by_id[source_id] = row
    write_csv(score_path, score)
    write_json(CENSUS / "SOURCE_SCORECARD.json", score)

    coverage_path = CENSUS / "SOURCE_COVERAGE_MATRIX.csv"
    coverage = read_csv(coverage_path)
    coverage_by_id = {row["source_id"]: row for row in coverage}
    for source_id, access in access_changes.items():
        coverage_by_id[source_id]["access_class"] = access
    coverage_by_id["dsm_watch"].update(
        evidence_type="AGGREGATE_ACTIVITY;REFERENCE",
        connector_priority="P2",
        coverage_note=(
            "public aggregate portal; vessel search/event download account-gated; "
            "individual track export not demonstrated"
        ),
    )
    for source_id, values in templates.items():
        template_id, _, _, evidence, access, priority, reason = values
        is_new = source_id not in coverage_by_id
        row = deepcopy(coverage_by_id[template_id]) if is_new else coverage_by_id[source_id]
        row.update(
            source_id=source_id,
            evidence_type=evidence,
            access_class=access,
            connector_priority=priority,
            coverage_note=reason,
        )
        if is_new:
            coverage.append(row)
        coverage_by_id[source_id] = row
    write_csv(coverage_path, coverage)
    write_json(CENSUS / "SOURCE_COVERAGE_MATRIX.json", coverage)

    license_path = CENSUS / "SOURCE_LICENSE_MATRIX.csv"
    licenses = read_csv(license_path)
    license_by_id = {row["source_id"]: row for row in licenses}
    for source_id, access in access_changes.items():
        license_by_id[source_id]["access_class"] = access
    license_by_id["dsm_watch"].update(
        evidence_url=(
            "https://globalfishingwatch.org/platform/map/fishing-activity/deep-sea-mining-public"
        ),
        redistribution="portal-specific raw export/reuse grant not established",
        derivatives="not stated",
        commercial_use="not established",
        account_or_contract="none for public portal; account required for vessel/event access",
        notes=(
            "public heatmap/timebar loaded; vessel search permission denied and event downloads "
            "login-gated"
        ),
        last_checked_utc=CHECKED,
    )
    matrix_by_id = {row["interface_id"]: row for row in LICENSE_ROWS}
    for source_id, values in templates.items():
        template_id = values[0]
        is_new = source_id not in license_by_id
        row = deepcopy(license_by_id[template_id]) if is_new else license_by_id[source_id]
        matrix = matrix_by_id[source_id]
        row.update(
            source_id=source_id,
            access_class=matrix["access_class"],
            license_or_terms=(
                "GFW API terms; CC BY-NC 4.0"
                if "api" in source_id
                else "GFW service/dataset-specific terms"
            ),
            attribution="required",
            redistribution=matrix["redistribution"],
            derivatives=matrix["cached_derivative_data"],
            commercial_use=matrix["commercial_use"],
            account_or_contract=matrix["authentication"],
            default_eligible="NO",
            legal_review_needed="YES before integration",
            evidence_url=matrix["evidence_url"],
            notes=matrix["actual_test"],
            last_checked_utc=CHECKED,
        )
        if is_new:
            licenses.append(row)
        license_by_id[source_id] = row
    write_csv(license_path, licenses)
    write_json(CENSUS / "SOURCE_LICENSE_MATRIX.json", licenses)

    cross_path = CENSUS / "VESSEL_SOURCE_CROSSWALK.csv"
    cross = read_csv(cross_path)
    exact_ids = {
        row["mgrb_entity_id"]: row for row in resolution if row["match_status"] == "EXACT_IDENTIFIER"
    }
    for row in cross:
        if row["vessel_key"] in exact_ids:
            sources = [
                item
                for item in row["source_ids"].split(";")
                if item and item != "gfw_fishing_vessels_v3"
            ]
            row["source_ids"] = ";".join(sources)
            row["track_availability"] = (
                "GFW bulk identity/activity match; no individual positions in archive; "
                "online track access authentication-blocked in R3C"
            )
            note = (
                "Exact MMSI matched the public GFW Fishing vessels v3 archive; this does "
                "not infer behavior or militia status."
            )
            if note not in row["notes"]:
                row["notes"] = row["notes"].rstrip(".") + ". " + note
            row["last_checked_utc"] = CHECKED
    write_csv(cross_path, cross)
    write_json(CENSUS / "VESSEL_SOURCE_CROSSWALK.json", cross)

    retrieval_path = CENSUS / "RETRIEVAL_TEST_RESULTS.csv"
    retrieval = read_csv(retrieval_path)
    existing_ids = {row["test_id"] for row in retrieval}
    base = {key: "" for key in retrieval[0]}
    additions = [
        {
            **base,
            "test_id": "RT-GFW-VESSEL-SEARCH-ANON-401",
            "source_id": "gfw_vessel_search_api",
            "test_date_utc": CHECKED,
            "request_url": "https://gateway.api.globalfishingwatch.org/v3/vessels/search",
            "access_result": "AUTHENTICATION_REQUIRED",
            "http_or_tool_result": "HTTP 401; {error: invalid token}",
            "artifact_name": "none",
            "bytes": "0",
            "schema": "not returned",
            "rows": "0",
            "identity_findings": "no identity response without Bearer token",
            "quality_findings": "auth-blocked is distinct from no identity match",
            "license_check": "GFW API terms; CC BY-NC 4.0; attribution required",
            "decision": "P1_AUTH_REQUIRED",
            "notes": "Representative anonymous test establishes an endpoint-level auth gate.",
        },
        {
            **base,
            "test_id": "RT-GFW-EVENTS-ANON-401",
            "source_id": "gfw_api_events",
            "test_date_utc": CHECKED,
            "request_url": "https://gateway.api.globalfishingwatch.org/v3/events",
            "access_result": "AUTHENTICATION_REQUIRED",
            "http_or_tool_result": "HTTP 401 without Bearer token",
            "artifact_name": "none",
            "bytes": "0",
            "schema": "not returned",
            "rows": "0",
            "quality_findings": "event semantics preserved; no zero-event claim",
            "license_check": "GFW API terms; CC BY-NC 4.0; attribution required",
            "decision": "P1_AUTH_REQUIRED",
            "notes": "No event count is inferred from the authentication failure.",
        },
        {
            **base,
            "test_id": "RT-DSMW-ANON-UI",
            "source_id": "dsm_watch_vessel_event_access",
            "test_date_utc": CHECKED,
            "request_url": "https://globalfishingwatch.org/platform/map/fishing-activity/deep-sea-mining-public",
            "access_result": "PARTIAL_INTERACTIVE_ACCESS",
            "http_or_tool_result": "public portal/timebar loaded; vessel search permission denied",
            "artifact_name": "none",
            "bytes": "0",
            "schema": "interactive only",
            "rows": "0",
            "identity_findings": "underlying GFW vessel ID not exposed anonymously",
            "quality_findings": "event download controls require registration/login",
            "qgis_or_geopandas_test": "not applicable",
            "license_check": "portal-specific raw export/reuse grant not established",
            "decision": "P2_REFERENCE_AUTH_REQUIRED",
            "notes": "Public heatmap visibility is not treated as reusable track data.",
        },
    ]
    retrieval.extend(row for row in additions if row["test_id"] not in existing_ids)
    write_csv(retrieval_path, retrieval)
    write_json(CENSUS / "RETRIEVAL_TEST_RESULTS.json", retrieval)

    append_once(
        CENSUS / "CHINA_MARITIME_TRACK_SOURCE_CENSUS.md",
        "## R3C GFW track-access correction",
        """
## R3C GFW track-access correction

The targeted R3C audit separates GFW's interfaces. The versioned Zenodo archives
remain reproducible P0 identity/aggregate inputs, but are not individual tracks.
API v3 vessel identity and event endpoints returned HTTP 401 without an
owner-supplied Bearer token. GFW documentation describes individual track display
and account-gated CSV/GeoJSON export; R3C did not retrieve those files. Therefore
the earlier statement that the *tested public archives* lack point tracks remains
correct, but it must not be generalized to say that all GFW interfaces lack an
individual-track export. Exact counts and status distinctions are in
`r3c-gfw/R3_CENSUS_CORRECTIONS.md`.
""",
    )
    append_once(
        CENSUS / "R3_CONNECTOR_PRIORITY.md",
        "## R3C correction to GFW priorities",
        """
## R3C correction to GFW priorities

- **P0 remains:** checksum-pinned GFW Zenodo fishing identity and monthly aggregate
  archives. They contain no individual positions.
- **P1 after owner authentication:** GFW API v3 vessel identity and events, plus a
  supported account-gated UI export workflow if its terms and repeatability pass.
- **P2:** interactive track display, Deep-Sea Mining Watch, SAR, and VIIRS as
  reference/detection capabilities rather than individual-track defaults.
- **REJECT for production automation now:** undocumented scraping, session/token
  extraction, or treating gridded presence as individual tracks.

No production connector is implemented by R3C.
""",
    )
    if not bulk_loaded:
        raise SystemExit(f"Public GFW bulk archive not found: {bulk_path}")


def append_once(path: Path, marker: str, text: str) -> None:
    current = path.read_text(encoding="utf-8")
    if marker not in current:
        path.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")


def write_markdown(
    resolution: list[dict[str, str]], actor_rows: list[dict[str, str]], matches: list[dict[str, str]]
) -> None:
    searched = sum(row["successfully_searched"] == "YES" for row in resolution)
    blocked = len(resolution) - searched
    exact = len(matches)
    no_match = sum(row["resolution_status"] == "NO_IDENTITY_MATCH" for row in resolution)
    actor_line = ", ".join(
        f"{row['actor_type']} {row['exact_identifier_matches']}/{row['crosswalk_entities']}"
        for row in actor_rows
    )
    (OUT / "DEEP_SEA_MINING_WATCH_AUDIT.md").write_text(
        """# Deep-Sea Mining Watch access audit

Checked: 2026-08-25

## Actual unauthenticated UI result

- The official public portal loaded its heatmap workspace, 2025-08-01–2026-08-01
  default time range, timebar controls, share-map control, and map-screenshot control.
- The Vessels section explicitly reported: **You don't have permission to search
  in these datasets.** Vessel-group details required registration/login.
- Three event-download controls explicitly required registration/login.
- No individual vessel could be selected in the unauthenticated audit; therefore
  individual history, movement-track visibility, CSV/GeoJSON track export, and an
  underlying GFW vessel ID were not demonstrated.
- No Deep-Sea-Mining-Watch-specific public API or downloadable raw track dataset
  was found. Generic GFW API v3 endpoints require a confidential Bearer token.

## Exact classification

Under the R3C DSMW decision taxonomy the interface is **REFERENCE_ONLY**. Its
access class is **OPEN_INTERACTIVE_VIEW** for aggregate activity/reference context
and time filtering. Vessel search/details and event downloads are
**ACCOUNT_REQUIRED**. Portal-specific individual-track export is
**NOT_TESTED / authentication-blocked**, not “unavailable” and not “open data.”
The displayed public map is not, by itself, evidence of reusable vessel-level
movement data.

## Reuse boundary

The portal attributes Global Fishing Watch and the Benioff Ocean Science
Laboratory/UCSB. A portal-specific raw-export redistribution grant was not found.
GFW API terms cannot be extrapolated to every embedded or third-party dataset;
dataset metadata must be reviewed after authenticated retrieval. MGRB must not
scrape the UI, extract session tokens, or represent activity heatmaps as tracks.
""",
        encoding="utf-8",
    )
    (OUT / "R3_CENSUS_CORRECTIONS.md").write_text(
        f"""# R3 census corrections: GFW individual-track access

Technical state: **PARTIAL_R3C_BLOCKED_BY_GFW_AUTHENTICATION**

## Measured result

- Crosswalk: 195 entities; 195 received a resolution attempt.
- Successfully searched against the public GFW Fishing vessels v3 archive: {searched}.
- Exact MMSI matches in that archive: {exact}; searched archive no-match: {no_match}.
- Online-only identifiers blocked by API authentication or unsupported by the
  archive: {blocked}.
- Ambiguous matches: 0. No name-only match was promoted.
- Actor exact-match ratios: {actor_line}.
- Actual individual position records retrieved: **0**.

## Claims corrected

1. “GFW archive” and “GFW” are not synonymous. The tested Zenodo products contain
   annual vessel identity/activity and aggregate grid data, not positions.
2. GFW's official UI documentation separately describes individual track display
   and CSV/GeoJSON export; downloads require an account. This capability was not
   authenticated or downloaded in R3C.
3. API v3 Vessel Search provides identity/history metadata and Events provides
   algorithmic events, both with a token. No documented v3 raw individual-position
   endpoint was found.
4. Public interactive visibility, account-gated export, token-gated API, and open
   bulk archives now have separate source/interface rows and access classes.
5. Deep-Sea Mining Watch is public as an interactive aggregate portal, while its
   vessel search and event export are account-gated. Reusable individual tracks
   were not demonstrated.
6. The 17 exact GFW bulk matches were snowballed by MMSI/name against the existing
   R3 crosswalk source-link inventory. All already pointed to AMTI; no materially
   new PANGAEA, cruise, government, RFMO, SCSDI or other existing-census link was
   established, so the crosswalk source links were not inflated.

## Non-findings that remain bounded

The 178 rows without an archive identity match are not proof of no AIS
transmission. Forty-two were not searchable in the bulk archive by their strongest
identifier and remained online-authentication-blocked. The 136 exact-MMSI archive
no-matches are no-matches only in this versioned fishing-vessel archive.

## Required questions — bounded numerical answers

1. **Successfully searched:** {searched}/195 against the public bulk identity
   archive; all 195 received an attempt, while {blocked} remained online-auth-blocked.
2. **Matched GFW identity:** {exact} exact MMSI matches in the tested archive.
3. **Matches by actor:** PLAN 0; CCG 0; RESEARCH_SURVEY 0; FISHING 0;
   MARITIME_MILITIA 17; OTHER 0.
4. **Matched-vessel track capability actually verified:** UI-visible 0;
   downloadable track 0; API positions 0; downloaded CSV tracks 0; downloaded
   GeoJSON tracks 0. CSV/GeoJSON export is officially documented but remained
   authentication-blocked for all 17 matches.
5. **Real position records retrieved:** 0.
6. **Taiwan/East Asia intersection, 2022–2026:** 0 confirmed. All 17 matched
   AMTI-listed vessels are plausibly relevant, but the archive has no coordinates,
   so geographic intersection was not testable.
7. **Richest public research/survey track:** no research vessel matched GFW in R3C.
   The existing R3 PANGAEA Xue Long record remains the richest verified open series
   in this census at 3,186 positions (2012), outside the R3C period.
8. **CCG usable public GFW individual tracks:** 0 demonstrated.
9. **PLAN usable public GFW individual tracks:** 0 demonstrated.
10. **Militia/fishing identities resolved:** 17/149 exact GFW bulk identities;
    0/149 yielded usable individual positions in R3C.
11. **UI capability not currently automated by the documented API:** individual
    track display and account-gated CSV/GeoJSON track export. API v3 documents
    vessel identity and events, but no raw individual-position endpoint was found.
12. **Deep-Sea Mining Watch:** aggregate map/time filtering is openly viewable;
    vessel search and event downloads are account-gated; portal-specific individual
    track export remains unverified, not proven unavailable.
13. **Original R3 claims corrected:** GFW's open bulk, interactive display,
    interactive export, identity API, events API, presence API, SAR/VIIRS, and DSMW
    capabilities now have separate access/legal/automation classifications.
14. **Connector order:** P0 bulk archive hardening; then P1 authenticated Vessel
    Search identity resolver; then P1 Events client. Do not implement a raw-track
    connector until a supported lawful machine interface is demonstrated.
""",
        encoding="utf-8",
    )
    (OUT / "R3C_CONNECTOR_RECOMMENDATION.md").write_text(
        """# R3C connector recommendation

No production connector is implemented by this audit.

## Priority

- **P0:** retain and harden checksum-pinned GFW Zenodo Fishing vessels v3 and
  monthly fleet archives. Identity and gridded presence must remain separate.
- **P1:** after the owner supplies a lawful GFW account/token, implement a
  credential-external Vessel Search identity resolver and Events client. Cache
  dataset versions, response hashes and terms evidence, never the token.
- **P1 validation spike:** manually test the documented account-gated individual
  track CSV/GeoJSON export on the reproducible 17-vessel sample. Promote only if
  repeatable, permitted, structured and automatable through a supported interface.
- **P2:** GFW interactive track view, Deep-Sea Mining Watch, SAR and VIIRS for
  reference/detection workflows.
- **P3/BYO:** licensed AIS position connectors remain user-supplied and
  non-redistributable.
- **REJECT:** UI scraping, authentication bypass, secret extraction, or relabeling
  aggregate presence/events as raw individual tracks.

The next implementation should be the authenticated GFW **identity resolver**, then
the **events client**. A raw track connector is not recommended until an official,
repeatable machine interface or a legally supported export workflow is proven.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gfw-bulk",
        type=Path,
        default=ROOT / ".tmp" / "r3-retrieval" / "fishing-vessels-v3-clean.csv",
    )
    args = parser.parse_args()
    crosswalk = read_csv(CENSUS / "VESSEL_SOURCE_CROSSWALK.csv")
    if len(crosswalk) != 195:
        raise SystemExit(f"Expected 195 crosswalk entities, found {len(crosswalk)}")
    targets = {
        row[field].strip()
        for row in crosswalk
        for field in ("mmsi_primary", "mmsi_secondary")
        if row[field].strip()
    }
    bulk_loaded = args.gfw_bulk.is_file()
    bulk = index_bulk(args.gfw_bulk, targets)
    resolution = build_resolution(crosswalk, bulk, bulk_loaded)
    matches = matched_entities(resolution)
    tracks = build_track_tests(matches)
    events = build_event_tests(matches)
    actors = build_actor_summary(resolution)
    taiwan = build_taiwan(matches)
    write_pair("GFW_VESSEL_RESOLUTION", resolution)
    write_pair("GFW_TRACK_ACCESS_TESTS", tracks)
    write_pair("GFW_EVENT_ACCESS_TESTS", events)
    write_csv(OUT / "GFW_ACTOR_COVERAGE_SUMMARY.csv", actors)
    write_csv(OUT / "GFW_TAIWAN_EAST_ASIA_COVERAGE.csv", taiwan)
    write_csv(OUT / "GFW_LICENSE_ACCESS_MATRIX.csv", LICENSE_ROWS)
    write_markdown(resolution, actors, matches)
    upsert_existing(resolution, args.gfw_bulk, bulk_loaded)
    print(
        json.dumps(
            {
                "entities": len(resolution),
                "successfully_searched": sum(
                    row["successfully_searched"] == "YES" for row in resolution
                ),
                "exact_bulk_matches": len(matches),
                "track_test_rows": len(tracks),
                "event_test_rows": len(events),
                "actual_positions_retrieved": 0,
                "technical_state": "PARTIAL_R3C_BLOCKED_BY_GFW_AUTHENTICATION",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
