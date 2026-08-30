from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from .evidence import QualityControlConfig, normalize_evidence, quality_control
from .provenance import sha256
from .vessels import VesselRegistry

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "latitude": ("latitude", "lat", "y", "ycoord", "ycoordinate"),
    "longitude": ("longitude", "lon", "lng", "long", "x", "xcoord", "xcoordinate"),
    "timestamp_start": (
        "timestamp",
        "datetime",
        "date_time",
        "time",
        "position_time",
        "observed_at",
        "timestamp_start",
    ),
    "entity_id": ("entity_id", "vessel_id", "ship_id", "track_id", "id"),
    "MMSI": ("mmsi",),
    "IMO": ("imo", "imo_number"),
    "vessel_name": ("vessel_name", "ship_name", "vessel", "ship", "name"),
    "speed": ("speed", "sog", "speed_knots", "speed_over_ground"),
    "course": ("course", "cog", "course_over_ground"),
    "heading": ("heading", "hdg"),
    "depth": ("depth", "water_depth", "depth_m"),
    "source_segment_id": ("seg_id", "segment_id", "source_segment_id"),
}

SUPPORTED_SUFFIXES = {".csv", ".tsv", ".geojson", ".json", ".gpkg", ".shp"}
CRITICAL_FIELDS = ("latitude", "longitude", "timestamp_start")
IDENTITY_FIELDS = ("entity_id", "MMSI", "IMO", "vessel_name")


def _token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


@dataclass(frozen=True)
class InputInspection:
    filename: str
    format: str
    sha256: str
    record_count: int
    columns: tuple[str, ...]
    detected_fields: dict[str, str]
    confidence: str
    requires_confirmation: bool
    reasons: tuple[str, ...]
    bbox_wgs84: tuple[float, float, float, float] | None
    temporal_coverage: tuple[str | None, str | None]
    sample_positions: tuple[tuple[float, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported input format {path.suffix!r}; use CSV, GeoJSON, GeoPackage, or Shapefile"
        )
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError("Geospatial input has no CRS; assign a CRS before importing")
    return frame.to_crs(4326)


def _detect(columns: list[str]) -> tuple[dict[str, str], list[str]]:
    normalized: dict[str, list[str]] = {}
    for column in columns:
        normalized.setdefault(_token(column), []).append(column)
    mapping: dict[str, str] = {}
    reasons: list[str] = []
    for canonical, aliases in FIELD_ALIASES.items():
        matches: list[str] = []
        for alias in aliases:
            matches.extend(normalized.get(_token(alias), []))
        matches = list(dict.fromkeys(matches))
        if len(matches) == 1:
            mapping[canonical] = matches[0]
        elif len(matches) > 1:
            reasons.append(f"Ambiguous {canonical}: {', '.join(matches)}")
    return mapping, reasons


def inspect_input(path: Path) -> InputInspection:
    path = path.resolve()
    frame = _read_input(path)
    columns = [str(column) for column in frame.columns if str(column) != "geometry"]
    mapping, reasons = _detect(columns)
    if isinstance(frame, gpd.GeoDataFrame) and "geometry" in frame:
        geometry_types = set(frame.geometry.dropna().geom_type)
        if geometry_types and geometry_types <= {"Point", "MultiPoint"}:
            mapping.setdefault("longitude", "__geometry__")
            mapping.setdefault("latitude", "__geometry__")
    for field in CRITICAL_FIELDS:
        if field not in mapping:
            reasons.append(f"Missing required field: {field}")
    if not any(field in mapping for field in IDENTITY_FIELDS):
        reasons.append("Missing vessel/entity identity field")

    longitude = None
    latitude = None
    if mapping.get("longitude") == "__geometry__":
        longitude = frame.geometry.x
        latitude = frame.geometry.y
    elif "longitude" in mapping and "latitude" in mapping:
        longitude = pd.to_numeric(frame[mapping["longitude"]], errors="coerce")
        latitude = pd.to_numeric(frame[mapping["latitude"]], errors="coerce")
    valid = None
    bbox = None
    samples: tuple[tuple[float, float], ...] = ()
    if longitude is not None and latitude is not None:
        valid = pd.DataFrame({"lon": longitude, "lat": latitude}).dropna()
        valid = valid[valid.lon.between(-180, 180) & valid.lat.between(-90, 90)]
        if not valid.empty:
            bbox = (
                float(valid.lon.min()),
                float(valid.lat.min()),
                float(valid.lon.max()),
                float(valid.lat.max()),
            )
            stride = max(1, len(valid) // 400)
            samples = tuple(
                (float(row.lon), float(row.lat))
                for row in valid.iloc[::stride].itertuples(index=False)
            )[:400]

    first = last = None
    if "timestamp_start" in mapping:
        times = pd.to_datetime(frame[mapping["timestamp_start"]], errors="coerce", utc=True)
        if times.notna().any():
            first = times.min().isoformat()
            last = times.max().isoformat()
    confidence = "HIGH" if not reasons else "NEEDS_CONFIRMATION"
    return InputInspection(
        filename=path.name,
        format=path.suffix.casefold().lstrip("."),
        sha256=sha256(path),
        record_count=len(frame),
        columns=tuple(columns),
        detected_fields=mapping,
        confidence=confidence,
        requires_confirmation=bool(reasons),
        reasons=tuple(reasons),
        bbox_wgs84=bbox,
        temporal_coverage=(first, last),
        sample_positions=samples,
    )


def _stable_local_entity(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"user-{digest}"


def normalize_user_input(
    path: Path,
    *,
    build_id: str,
    field_map: dict[str, str] | None = None,
    source_name: str | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    inspection = inspect_input(path)
    mapping = dict(inspection.detected_fields)
    if field_map:
        mapping.update(field_map)
    missing = [field for field in CRITICAL_FIELDS if field not in mapping]
    if not any(field in mapping for field in IDENTITY_FIELDS):
        missing.append("entity identity")
    if missing:
        raise ValueError("Schema confirmation required: " + ", ".join(missing))
    loaded = _read_input(path)
    if mapping.get("longitude") == "__geometry__":
        mapping.pop("longitude", None)
        mapping.pop("latitude", None)
    identity_source = next(field for field in IDENTITY_FIELDS if field in mapping)
    if identity_source != "entity_id":
        loaded = loaded.copy()
        loaded["__mgrb_entity_id"] = loaded[mapping[identity_source]].map(_stable_local_entity)
        mapping["entity_id"] = "__mgrb_entity_id"
    elif mapping["entity_id"] != "entity_id":
        loaded = loaded.copy()
        loaded["__mgrb_entity_id"] = loaded[mapping["entity_id"]].map(_stable_local_entity)
        mapping["entity_id"] = "__mgrb_entity_id"
    loaded = loaded.copy()
    loaded["__mgrb_actor_type"] = "UNKNOWN"
    mapping["actor_type"] = "__mgrb_actor_type"
    normalized = normalize_evidence(
        loaded,
        VesselRegistry([]),
        build_id=build_id,
        source_type="USER_SUPPLIED",
        source_name=source_name or path.name,
        field_map=mapping,
        license_text="USER_SUPPLIED_REVIEW_REQUIRED",
        attribution="User-supplied local data",
        raw_reference=path.name,
    )
    qc = quality_control(normalized, QualityControlConfig())
    summary = {
        "schema": inspection.to_dict(),
        "cleaned_positions": len(qc.cleaned_points),
        "excluded_positions": len(qc.excluded_points),
        "duplicate_positions": int((qc.quality_flags["flag"] == "DUPLICATE_OBSERVATION").sum()),
        "invalid_coordinates": int((qc.quality_flags["flag"] == "INVALID_COORDINATE").sum()),
        "invalid_timestamps": int((qc.quality_flags["flag"] == "MISSING_TIME").sum()),
        "large_gaps": len(qc.gaps),
        "track_segments": len(qc.track_segments),
        "source_sha256": inspection.sha256,
    }
    return normalized, summary


def inspection_json(path: Path) -> str:
    return json.dumps(inspect_input(path).to_dict(), indent=2, sort_keys=True)
