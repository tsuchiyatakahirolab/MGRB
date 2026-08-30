from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from .evidence import normalize_evidence
from .provenance import sha256
from .vessels import VesselRegistry

OBSERVATION_METHODS = {
    "EXACT_COORDINATE",
    "TEXT_RELATIVE_POSITION",
    "MAP_DERIVED_POSITION",
    "APPROXIMATE_POSITION",
}


@dataclass(frozen=True)
class OfficialObservationSummary:
    source_sha256: str
    record_count: int
    exact_count: int
    approximate_count: int
    map_derived_count: int
    first_timestamp: str | None
    last_timestamp: str | None
    continuous_track_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def import_official_observations(
    path: Path,
    *,
    build_id: str,
    field_map: dict[str, str] | None = None,
    source_name: str | None = None,
    license_text: str = "SOURCE_SPECIFIC_REVIEW_REQUIRED",
    attribution: str = "Original issuing authority and source URL per record",
) -> tuple[gpd.GeoDataFrame, OfficialObservationSummary]:
    suffix = path.suffix.casefold()
    if suffix in {".csv", ".tsv"}:
        loaded: pd.DataFrame = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    elif suffix in {".geojson", ".json", ".gpkg", ".shp"}:
        loaded = gpd.read_file(path)
        if loaded.crs is None:
            raise ValueError("Official observation input has no CRS")
        loaded = loaded.to_crs(4326)
    else:
        raise ValueError(f"Unsupported official observation format: {path.suffix}")
    normalized = normalize_evidence(
        loaded,
        VesselRegistry([]),
        build_id=build_id,
        source_type="OFFICIAL_OBSERVATION",
        source_name=source_name or path.name,
        field_map=field_map,
        license_text=license_text,
        attribution=attribution,
        raw_reference=path.name,
    )
    methods = normalized["observation_method"].astype(str).str.upper()
    invalid = sorted(set(methods) - OBSERVATION_METHODS)
    if invalid:
        raise ValueError(f"Unsupported official observation method(s): {invalid}")
    normalized["observation_method"] = methods
    normalized["map_derived"] = methods.eq("MAP_DERIVED_POSITION")
    normalized["position_exact"] = methods.eq("EXACT_COORDINATE")
    uncertainty = pd.to_numeric(normalized["position_uncertainty_m"], errors="coerce")
    if uncertainty[~normalized["position_exact"]].isna().any():
        raise ValueError("Approximate/map-derived observations require position_uncertainty_m")
    if normalized["source_url"].fillna("").str.strip().eq("").any():
        raise ValueError("Every official observation requires source_url")
    times = pd.to_datetime(normalized["timestamp_start"], errors="coerce", utc=True)
    if times.isna().any():
        raise ValueError("Every official observation requires a valid timestamp_start")
    summary = OfficialObservationSummary(
        source_sha256=sha256(path),
        record_count=len(normalized),
        exact_count=int(normalized["position_exact"].sum()),
        approximate_count=int((~normalized["position_exact"]).sum()),
        map_derived_count=int(normalized["map_derived"].sum()),
        first_timestamp=times.min().isoformat() if len(times) else None,
        last_timestamp=times.max().isoformat() if len(times) else None,
    )
    return normalized, summary
