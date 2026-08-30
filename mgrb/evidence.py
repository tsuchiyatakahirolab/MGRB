from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from pyproj import Geod
from shapely.geometry import LineString, Point

from .vessels import VesselRegistry, identifier_is_malformed

EVIDENCE_TYPES = {
    "AIS",
    "PUBLIC_TRACK",
    "OFFICIAL_OBSERVATION",
    "SAR_DETECTION",
    "OPTICAL_DETECTION",
    "VIIRS_BOAT_DETECTION",
    "PORT_RECORD",
    "USER_SUPPLIED",
    "LICENSED_EXTERNAL",
}
ACTOR_TYPES = {
    "PLAN",
    "CCG",
    "RESEARCH_SURVEY",
    "FISHING",
    "MARITIME_MILITIA",
    "MSA",
    "OTHER_GOVERNMENT",
    "UNKNOWN",
}
OBSERVATION_STATES = {"OBSERVED", "INTERPOLATED_SHORT_GAP", "INFERRED_ROUTE", "UNKNOWN"}
SEGMENT_TYPES = {"OBSERVED_TRACK", "SHORT_INTERPOLATION", "INFERRED_CONNECTION"}
CANONICAL_COLUMNS = (
    "observation_id",
    "entity_id",
    "timestamp_start",
    "timestamp_end",
    "latitude",
    "longitude",
    "actor_type",
    "vessel_name",
    "hull_number",
    "IMO",
    "MMSI",
    "source_type",
    "source_name",
    "source_record_id",
    "source_url",
    "source_date",
    "observation_method",
    "identity_confidence",
    "position_confidence",
    "observed_or_inferred",
    "position_uncertainty_m",
    "temporal_uncertainty_s",
    "license",
    "attribution",
    "raw_record_reference",
    "processing_notes",
    "source_segment_id",
    "build_id",
)
SEGMENT_COLUMNS = (
    "segment_id",
    "entity_id",
    "start_observation_id",
    "end_observation_id",
    "start_entity_id",
    "end_entity_id",
    "actor_type",
    "start_time",
    "end_time",
    "segment_type",
    "point_count",
    "max_gap_seconds",
    "confidence",
    "source_set",
    "source_segment_ids",
)
DEFAULT_ALIASES = {
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "lng", "x"),
    "timestamp_start": ("timestamp_start", "timestamp", "datetime", "time", "date"),
    "vessel_name": ("vessel_name", "name", "ship_name"),
    "MMSI": ("MMSI", "mmsi"),
    "IMO": ("IMO", "imo"),
    "hull_number": ("hull_number", "hull", "pennant"),
    "source_segment_id": ("source_segment_id", "seg_id", "segment_id"),
}
GEOD = Geod(ellps="WGS84")
DENSE_OBSERVED_SOURCE_TYPES = {"AIS", "PUBLIC_TRACK", "USER_SUPPLIED"}


@dataclass(frozen=True)
class QualityControlConfig:
    max_speed_knots: float = 80.0
    observed_track_max_gap_seconds: int = 3600
    large_gap_seconds: int = 21600
    allow_short_gap_interpolation: bool = False
    short_gap_interpolation_seconds: int = 10800
    inferred_connection_max_gap_seconds: int = 7 * 86400


@dataclass
class QualityControlResult:
    cleaned_points: gpd.GeoDataFrame
    excluded_points: gpd.GeoDataFrame
    quality_flags: pd.DataFrame
    gaps: pd.DataFrame
    track_segments: gpd.GeoDataFrame
    vessel_summary: pd.DataFrame


def _empty_points() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(columns=[*CANONICAL_COLUMNS, "geometry"], geometry="geometry", crs=4326)


def _empty_segments() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(columns=[*SEGMENT_COLUMNS, "geometry"], geometry="geometry", crs=4326)


def _stable_observation_id(source: str, index: int, row: Mapping[str, object]) -> str:
    payload = json.dumps(
        {
            "source": source,
            "index": index,
            "time": str(row.get("timestamp_start", "")),
            "lat": str(row.get("latitude", "")),
            "lon": str(row.get("longitude", "")),
            "identity": str(row.get("entity_id") or row.get("MMSI") or row.get("vessel_name")),
        },
        sort_keys=True,
    )
    return "obs-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _source_column(frame: pd.DataFrame, canonical: str, field_map: Mapping[str, str]) -> str | None:
    if canonical in field_map:
        return field_map[canonical]
    lowered = {str(column).casefold(): str(column) for column in frame.columns}
    for candidate in DEFAULT_ALIASES.get(canonical, (canonical,)):
        if candidate.casefold() in lowered:
            return lowered[candidate.casefold()]
    return None


def read_evidence(
    path: Path,
    registry: VesselRegistry,
    *,
    build_id: str,
    source_type: str = "USER_SUPPLIED",
    source_name: str | None = None,
    field_map: Mapping[str, str] | None = None,
    license_text: str = "USER_SUPPLIED_REVIEW_REQUIRED",
    attribution: str = "User-supplied local evidence",
) -> gpd.GeoDataFrame:
    """Read common BYO formats and normalize them without copying the source file."""
    suffix = path.suffix.casefold()
    if suffix in {".geojson", ".json", ".gpkg", ".shp"}:
        loaded = gpd.read_file(path)
        if loaded.crs is not None:
            loaded = loaded.to_crs(4326)
    elif suffix in {".csv", ".tsv"}:
        loaded = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    else:
        raise ValueError(f"Unsupported evidence format: {path.suffix}")
    return normalize_evidence(
        loaded,
        registry,
        build_id=build_id,
        source_type=source_type,
        source_name=source_name or path.name,
        field_map=field_map,
        license_text=license_text,
        attribution=attribution,
        raw_reference=str(path.resolve()),
    )


def normalize_evidence(
    loaded: pd.DataFrame,
    registry: VesselRegistry,
    *,
    build_id: str,
    source_type: str,
    source_name: str,
    field_map: Mapping[str, str] | None = None,
    license_text: str,
    attribution: str,
    raw_reference: str | None = None,
) -> gpd.GeoDataFrame:
    if source_type not in EVIDENCE_TYPES:
        raise ValueError(f"Unsupported evidence type: {source_type}")
    field_map = field_map or {}
    frame = loaded.copy()
    result = pd.DataFrame(index=frame.index)
    for canonical in CANONICAL_COLUMNS:
        source_column = _source_column(frame, canonical, field_map)
        result[canonical] = frame[source_column] if source_column else None
    if isinstance(frame, gpd.GeoDataFrame) and "geometry" in frame:
        result["longitude"] = result["longitude"].where(
            result["longitude"].notna(), frame.geometry.x
        )
        result["latitude"] = result["latitude"].where(result["latitude"].notna(), frame.geometry.y)
    result["source_type"] = result["source_type"].fillna(source_type)
    result["source_name"] = result["source_name"].fillna(source_name)
    result["source_record_id"] = result["source_record_id"].fillna(
        pd.Series([f"{source_name}:{index}" for index in result.index], index=result.index)
    )
    result["source_date"] = result["source_date"].fillna(
        pd.to_datetime(result["timestamp_start"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    )
    result["observation_method"] = result["observation_method"].fillna(source_type)
    result["identity_confidence"] = result["identity_confidence"].fillna("UNKNOWN")
    result["position_confidence"] = result["position_confidence"].fillna("UNKNOWN")
    result["observed_or_inferred"] = result["observed_or_inferred"].fillna("OBSERVED")
    result["license"] = result["license"].fillna(license_text)
    result["attribution"] = result["attribution"].fillna(attribution)
    if raw_reference is not None:
        result["raw_record_reference"] = result["raw_record_reference"].fillna(raw_reference)
    result["processing_notes"] = result["processing_notes"].fillna("Normalized by MGRB")
    result["build_id"] = build_id
    result["timestamp_end"] = result["timestamp_end"].where(
        result["timestamp_end"].notna(), result["timestamp_start"]
    )
    for index, row in result.iterrows():
        resolution = registry.resolve(row)
        if not row.get("entity_id") and resolution.entity_id:
            result.at[index, "entity_id"] = resolution.entity_id
            result.at[index, "identity_confidence"] = resolution.confidence
        entity_id = result.at[index, "entity_id"]
        if entity_id in registry.by_id:
            entity = registry.get(str(entity_id))
            result.at[index, "actor_type"] = entity["actor_type"]
            if not result.at[index, "vessel_name"]:
                result.at[index, "vessel_name"] = entity["canonical_name"]
        if not result.at[index, "observation_id"]:
            result.at[index, "observation_id"] = _stable_observation_id(source_name, index, row)
    result["latitude"] = pd.to_numeric(result["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(result["longitude"], errors="coerce")
    geometry = [
        Point(longitude, latitude) if pd.notna(longitude) and pd.notna(latitude) else None
        for longitude, latitude in zip(result["longitude"], result["latitude"], strict=False)
    ]
    normalized = gpd.GeoDataFrame(result, geometry=geometry, crs=4326)
    normalized["_source_order"] = range(len(normalized))
    return normalized


def _add_flag(
    flags: list[dict[str, object]],
    row: pd.Series,
    flag: str,
    severity: str,
    detail: str,
    excluded: bool,
) -> None:
    flags.append(
        {
            "observation_id": row.get("observation_id"),
            "entity_id": row.get("entity_id"),
            "flag": flag,
            "severity": severity,
            "detail": detail,
            "excluded": excluded,
        }
    )


def quality_control(
    observations: gpd.GeoDataFrame,
    config: QualityControlConfig | None = None,
) -> QualityControlResult:
    config = config or QualityControlConfig()
    frame = observations.copy()
    if frame.empty:
        return QualityControlResult(
            _empty_points(),
            _empty_points(),
            pd.DataFrame(
                columns=["observation_id", "entity_id", "flag", "severity", "detail", "excluded"]
            ),
            pd.DataFrame(columns=["entity_id", "start_time", "end_time", "gap_seconds"]),
            _empty_segments(),
            pd.DataFrame(
                columns=[
                    "entity_id",
                    "actor_type",
                    "observation_count",
                    "first_seen",
                    "last_seen",
                    "flag_count",
                ]
            ),
        )
    frame["_source_order"] = frame.get(
        "_source_order", pd.Series(range(len(frame)), index=frame.index)
    )
    frame["_time"] = pd.to_datetime(frame["timestamp_start"], errors="coerce", utc=True)
    excluded_indices: set[Any] = set()
    flags: list[dict[str, object]] = []

    for index, row in frame.iterrows():
        latitude, longitude = row.get("latitude"), row.get("longitude")
        if (
            pd.isna(latitude)
            or pd.isna(longitude)
            or not (-90 <= latitude <= 90)
            or not (-180 <= longitude <= 180)
        ):
            _add_flag(
                flags,
                row,
                "INVALID_COORDINATE",
                "ERROR",
                "Coordinate is missing or outside WGS84 bounds",
                True,
            )
            excluded_indices.add(index)
        if pd.isna(row["_time"]):
            _add_flag(
                flags, row, "MISSING_TIME", "ERROR", "No parseable observation timestamp", True
            )
            excluded_indices.add(index)
        if not str(row.get("entity_id") or "").strip():
            _add_flag(
                flags, row, "MISSING_VESSEL_IDENTITY", "ERROR", "Entity resolution failed", True
            )
            excluded_indices.add(index)
        for identifier in ("MMSI", "IMO"):
            if identifier_is_malformed(identifier, row.get(identifier)):
                _add_flag(
                    flags, row, f"MALFORMED_{identifier}", "ERROR", f"Malformed {identifier}", True
                )
                excluded_indices.add(index)
        actor = str(row.get("actor_type") or "UNKNOWN")
        if actor not in ACTOR_TYPES:
            _add_flag(flags, row, "UNKNOWN_ACTOR_TYPE", "WARNING", actor, False)
        if str(row.get("observed_or_inferred") or "") not in OBSERVATION_STATES:
            _add_flag(
                flags,
                row,
                "UNKNOWN_OBSERVATION_STATE",
                "ERROR",
                str(row.get("observed_or_inferred")),
                True,
            )
            excluded_indices.add(index)

    duplicate_mask = frame.duplicated(
        subset=["entity_id", "timestamp_start", "latitude", "longitude", "source_record_id"],
        keep="first",
    )
    for index in frame.index[duplicate_mask]:
        _add_flag(
            flags,
            frame.loc[index],
            "DUPLICATE_OBSERVATION",
            "ERROR",
            "Exact canonical duplicate",
            True,
        )
        excluded_indices.add(index)

    gaps: list[dict[str, object]] = []
    for entity_id, source_group in frame.sort_values("_source_order").groupby(
        "entity_id", dropna=False
    ):
        previous_time = None
        for _, row in source_group.iterrows():
            current = row["_time"]
            if previous_time is not None and pd.notna(current) and current < previous_time:
                _add_flag(
                    flags,
                    row,
                    "TIMESTAMP_DISORDER",
                    "WARNING",
                    "Input order decreases in time",
                    False,
                )
            if pd.notna(current):
                previous_time = current

        chronological = source_group.sort_values("_time")
        previous = None
        for index, row in chronological.iterrows():
            if previous is None or index in excluded_indices:
                previous = (index, row)
                continue
            previous_index, previous_row = previous
            if previous_index in excluded_indices:
                previous = (index, row)
                continue
            gap_seconds = (row["_time"] - previous_row["_time"]).total_seconds()
            if gap_seconds <= 0:
                previous = (index, row)
                continue
            _, _, distance_m = GEOD.inv(
                float(previous_row["longitude"]),
                float(previous_row["latitude"]),
                float(row["longitude"]),
                float(row["latitude"]),
            )
            speed_knots = distance_m / gap_seconds * 1.9438444924406
            if distance_m < 1.0:
                _add_flag(
                    flags,
                    row,
                    "REPEATED_IDENTICAL_POINT",
                    "WARNING",
                    "Sequential position repeats",
                    False,
                )
            if speed_knots > config.max_speed_knots:
                _add_flag(flags, row, "IMPOSSIBLE_SPEED", "ERROR", f"{speed_knots:.1f} knots", True)
                excluded_indices.add(index)
                continue
            if gap_seconds > config.large_gap_seconds:
                gaps.append(
                    {
                        "entity_id": entity_id,
                        "start_time": previous_row["timestamp_start"],
                        "end_time": row["timestamp_start"],
                        "gap_seconds": gap_seconds,
                    }
                )
                _add_flag(
                    flags,
                    row,
                    "LARGE_OBSERVATION_GAP",
                    "WARNING",
                    f"{gap_seconds:.0f} seconds",
                    False,
                )
            previous = (index, row)

    excluded = (
        frame.loc[sorted(excluded_indices)].copy() if excluded_indices else frame.iloc[0:0].copy()
    )
    cleaned = frame.drop(index=excluded_indices).copy()
    segments = _build_segments(cleaned, config)
    validate_segment_entity_integrity(segments)
    flags_frame = pd.DataFrame(
        flags,
        columns=["observation_id", "entity_id", "flag", "severity", "detail", "excluded"],
    )
    summaries = []
    for entity_id, group in cleaned.groupby("entity_id"):
        entity_flags = flags_frame[flags_frame["entity_id"] == entity_id]
        summaries.append(
            {
                "entity_id": entity_id,
                "actor_type": group["actor_type"].iloc[0],
                "observation_count": len(group),
                "first_seen": group["_time"].min().isoformat(),
                "last_seen": group["_time"].max().isoformat(),
                "flag_count": len(entity_flags),
            }
        )
    cleaned = cleaned.drop(columns=["_time", "_source_order"], errors="ignore")
    excluded = excluded.drop(columns=["_time", "_source_order"], errors="ignore")
    return QualityControlResult(
        cleaned,
        excluded,
        flags_frame,
        pd.DataFrame(gaps, columns=["entity_id", "start_time", "end_time", "gap_seconds"]),
        segments,
        pd.DataFrame(summaries),
    )


def _build_segments(
    cleaned: gpd.GeoDataFrame,
    config: QualityControlConfig,
) -> gpd.GeoDataFrame:
    records: list[dict[str, object]] = []
    for entity_id, group in cleaned.assign(
        _time=pd.to_datetime(cleaned["timestamp_start"], errors="coerce", utc=True)
    ).groupby("entity_id"):
        ordered = group.sort_values("_time")
        source_types = set(ordered["source_type"].astype(str))
        if source_types and source_types <= DENSE_OBSERVED_SOURCE_TYPES:
            run: list[pd.Series] = []
            for _, row in ordered.iterrows():
                if not run:
                    run = [row]
                    continue
                gap = (row["_time"] - run[-1]["_time"]).total_seconds()
                previous_source_segment = str(run[-1].get("source_segment_id") or "").strip()
                current_source_segment = str(row.get("source_segment_id") or "").strip()
                provider_segment_changed = (
                    bool(previous_source_segment)
                    and bool(current_source_segment)
                    and previous_source_segment != current_source_segment
                )
                if gap <= config.observed_track_max_gap_seconds and not provider_segment_changed:
                    run.append(row)
                    continue
                if len(run) >= 2:
                    records.append(_segment_record(entity_id, run, "OBSERVED_TRACK", "HIGH"))
                if (
                    config.allow_short_gap_interpolation
                    and gap <= config.short_gap_interpolation_seconds
                ):
                    records.append(
                        _segment_record(
                            entity_id,
                            [run[-1], row],
                            "SHORT_INTERPOLATION",
                            "MEDIUM",
                        )
                    )
                run = [row]
            if len(run) >= 2:
                records.append(_segment_record(entity_id, run, "OBSERVED_TRACK", "HIGH"))
        else:
            rows = [row for _, row in ordered.iterrows()]
            for first, second in pairwise(rows):
                gap = (second["_time"] - first["_time"]).total_seconds()
                if 0 < gap <= config.inferred_connection_max_gap_seconds:
                    records.append(
                        _segment_record(
                            entity_id,
                            [first, second],
                            "INFERRED_CONNECTION",
                            "LOW",
                        )
                    )
    if not records:
        return _empty_segments()
    return gpd.GeoDataFrame(records, geometry="geometry", crs=4326)


def _segment_record(
    entity_id: str,
    rows: list[pd.Series],
    segment_type: str,
    confidence: str,
) -> dict[str, object]:
    if segment_type not in SEGMENT_TYPES:
        raise ValueError(segment_type)
    entity = str(entity_id or "").strip()
    row_entities = {str(row.get("entity_id") or "").strip() for row in rows}
    if not entity or row_entities != {entity}:
        raise ValueError(
            "Track segments require one documented entity; cross-entity or unidentified "
            f"endpoints are invalid: segment={entity!r}, rows={sorted(row_entities)!r}"
        )
    times = [row["_time"] for row in rows]
    gaps = [(current - previous).total_seconds() for previous, current in pairwise(times)]
    observation_ids = [str(row["observation_id"]) for row in rows]
    digest = hashlib.sha256("|".join(observation_ids).encode("utf-8")).hexdigest()[:16]
    return {
        "segment_id": f"seg-{digest}",
        "entity_id": entity,
        "start_observation_id": observation_ids[0],
        "end_observation_id": observation_ids[-1],
        "start_entity_id": entity,
        "end_entity_id": entity,
        "actor_type": rows[0]["actor_type"],
        "start_time": times[0].isoformat(),
        "end_time": times[-1].isoformat(),
        "segment_type": segment_type,
        "point_count": len(rows),
        "max_gap_seconds": max(gaps, default=0.0),
        "confidence": confidence,
        "source_set": json.dumps(sorted({str(row["source_name"]) for row in rows})),
        "source_segment_ids": json.dumps(
            sorted(
                {
                    str(row.get("source_segment_id") or "").strip()
                    for row in rows
                    if str(row.get("source_segment_id") or "").strip()
                }
            )
        ),
        "geometry": LineString([(float(row["longitude"]), float(row["latitude"])) for row in rows]),
    }


def validate_segment_entity_integrity(segments: pd.DataFrame) -> None:
    """Reject every inferred/observed segment whose endpoint identities diverge."""
    if segments.empty:
        return
    required = {"entity_id", "start_entity_id", "end_entity_id", "segment_type"}
    missing = required - set(segments.columns)
    if missing:
        raise ValueError(f"Track segments lack endpoint identity fields: {sorted(missing)}")
    for _, row in segments.iterrows():
        identities = {
            str(row.get("entity_id") or "").strip(),
            str(row.get("start_entity_id") or "").strip(),
            str(row.get("end_entity_id") or "").strip(),
        }
        if "" in identities or len(identities) != 1:
            raise ValueError(
                "Cross-entity or unidentified track segment rejected: "
                f"{row.get('segment_id', '<unknown>')} {sorted(identities)!r}"
            )
