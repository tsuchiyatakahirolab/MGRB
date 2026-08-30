from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from .provenance import sha256


@dataclass(frozen=True)
class EventImportSummary:
    source_sha256: str
    record_count: int
    first_timestamp: str | None
    last_timestamp: str | None
    geometry_types: tuple[str, ...]
    track_semantics_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def import_events(
    path: Path,
    *,
    dataset_id: str,
    field_map: dict[str, str] | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    license_text: str = "USER_SUPPLIED_REVIEW_REQUIRED",
    attribution: str = "User-supplied event data",
) -> tuple[gpd.GeoDataFrame, EventImportSummary]:
    """Import event geometry without ever assigning position-track semantics."""
    suffix = path.suffix.casefold()
    if suffix in {".geojson", ".json", ".gpkg", ".shp"}:
        loaded: pd.DataFrame = gpd.read_file(path)
        if loaded.crs is None:
            raise ValueError("Event input has no CRS")
        loaded = loaded.to_crs(4326)
    elif suffix in {".csv", ".tsv"}:
        loaded = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    else:
        raise ValueError(f"Unsupported event format: {path.suffix}")
    mapping = field_map or {}

    def column(name: str, aliases: tuple[str, ...]) -> str | None:
        if name in mapping:
            return mapping[name]
        lowered = {str(value).casefold(): str(value) for value in loaded.columns}
        return next(
            (lowered[item.casefold()] for item in aliases if item.casefold() in lowered), None
        )

    time_column = column(
        "start_time", ("start_time", "timestamp_start", "timestamp", "time", "date")
    )
    end_column = column("end_time", ("end_time", "timestamp_end"))
    type_column = column("event_type", ("event_type", "type", "category"))
    entity_column = column("entity_id", ("entity_id", "mmsi", "vessel_id"))
    latitude_column = column("latitude", ("latitude", "lat", "y"))
    longitude_column = column("longitude", ("longitude", "lon", "lng", "x"))
    if time_column is None:
        raise ValueError("Event input requires a timestamp/start_time field")
    timestamps = pd.to_datetime(loaded[time_column], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError("Event input contains invalid timestamps")
    if isinstance(loaded, gpd.GeoDataFrame):
        geometry = loaded.geometry
    elif latitude_column and longitude_column:
        latitude = pd.to_numeric(loaded[latitude_column], errors="coerce")
        longitude = pd.to_numeric(loaded[longitude_column], errors="coerce")
        if latitude.isna().any() or longitude.isna().any():
            raise ValueError("Event input contains invalid coordinates")
        geometry = gpd.points_from_xy(longitude, latitude)
    else:
        raise ValueError("Event input requires geometry or latitude/longitude fields")
    result = gpd.GeoDataFrame(geometry=geometry, crs=4326)
    source = source_name or path.name
    result["event_id"] = [
        "event-" + hashlib.sha256(f"{dataset_id}|{index}|{timestamp}".encode()).hexdigest()[:20]
        for index, timestamp in enumerate(timestamps)
    ]
    result["dataset_id"] = dataset_id
    result["entity_id"] = loaded[entity_column].astype(str) if entity_column else ""
    result["actor_type"] = "UNKNOWN"
    result["event_type"] = loaded[type_column].astype(str) if type_column else "USER_EVENT"
    result["start_time"] = timestamps.map(lambda value: value.isoformat())
    if end_column:
        ends = pd.to_datetime(loaded[end_column], errors="coerce", utc=True)
        result["end_time"] = ends.map(lambda value: value.isoformat() if pd.notna(value) else None)
    else:
        result["end_time"] = result["start_time"]
    result["confidence"] = "SOURCE_REPORTED"
    result["source_type"] = "USER_EVENT"
    result["source_name"] = source
    result["source_url"] = source_url
    result["license"] = license_text
    result["attribution"] = attribution
    result["evidence_class"] = "EVENT_GEOMETRY"
    summary = EventImportSummary(
        source_sha256=sha256(path),
        record_count=len(result),
        first_timestamp=timestamps.min().isoformat() if len(timestamps) else None,
        last_timestamp=timestamps.max().isoformat() if len(timestamps) else None,
        geometry_types=tuple(sorted(result.geometry.dropna().geom_type.unique())),
    )
    return result, summary
