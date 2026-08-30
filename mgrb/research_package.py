from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import rasterio

from . import __version__
from .adapters import (
    MarineRegionsWFSAdapter,
    PangaeaXueLong2012Adapter,
    ScsdiSouthChinaSeaEventsAdapter,
    WorldBankTrafficDensityAdapter,
)
from .analytics import (
    distance_to_features,
    low_speed_candidates,
    repeated_area_visits,
    track_coverage_metrics,
    zone_crossing_candidates,
)
from .cartography import buffered_bbox, buffered_vector_bbox, resolve_layout_geometry
from .config import Region, load_profiles, load_regions, load_yaml
from .events import import_events
from .evidence import QualityControlConfig, normalize_evidence, quality_control
from .importer import normalize_user_input
from .infrastructure import WorldPortIndexAdapter, import_infrastructure
from .layer_registry import LayerRegistry
from .official_observations import import_official_observations
from .product import BACKGROUND_PRESETS
from .provenance import git_commit, sha256
from .sources import SourceRegistry
from .theme import resolve_theme
from .vessels import VesselRegistry

ACTOR_ALIASES = {
    "plan": "PLAN",
    "pla_navy": "PLAN",
    "ccg": "CCG",
    "coast_guard": "CCG",
    "research": "RESEARCH_SURVEY",
    "survey": "RESEARCH_SURVEY",
    "research_survey": "RESEARCH_SURVEY",
    "fishing": "FISHING",
    "maritime_militia": "MARITIME_MILITIA",
}


@dataclass(frozen=True)
class ResearchBuildRequest:
    area: str
    output_root: Path
    build_id: str
    start_date: date | None = None
    end_date: date | None = None
    actors: tuple[str, ...] = ()
    public_data: bool = True
    local_inputs: tuple[Path, ...] = ()
    live_sources: bool = True
    traffic_density: Path | None = None
    base_build_id: str | None = None
    background: str = "bathymetry"
    enabled_maritime_layers: tuple[str, ...] = (
        "eez_reference",
        "territorial_sea",
    )
    field_maps: dict[str, dict[str, str]] | None = None
    input_kinds: dict[str, str] | None = None
    input_metadata: dict[str, dict[str, str]] | None = None
    context_layers: tuple[str, ...] = ()
    include_public_observations: bool = True
    product_mode: bool = False
    regions_config: Path | None = None
    visible_footer: bool = True
    requested_outputs: tuple[str, ...] = ("preview", "paper", "media", "qgis")


@dataclass(frozen=True)
class PreparedResearchPackage:
    build_id: str
    package_dir: Path
    spec_path: Path
    observation_count: int
    segment_count: int
    source_warnings: tuple[str, ...]


def normalize_actor_names(values: Iterable[str]) -> tuple[str, ...]:
    normalized = []
    for value in values:
        token = value.strip().casefold().replace("-", "_").replace(" ", "_")
        canonical = ACTOR_ALIASES.get(token, value.strip().upper())
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def _write_geodataframe(frame: gpd.GeoDataFrame, path: Path, layer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    append = path.exists()
    frame.to_file(path, layer=layer, driver="GPKG", index=False, mode="a" if append else "w")


def _write_nonspatial(frame: pd.DataFrame, path: Path, layer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pyogrio.write_dataframe(frame, path, layer=layer, driver="GPKG", append=path.exists())


def _embed_gpkg_metadata(path: Path, payload: dict) -> None:
    if not path.exists():
        return
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS gpkg_metadata (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              md_scope TEXT NOT NULL DEFAULT 'dataset',
              md_standard_uri TEXT NOT NULL,
              mime_type TEXT NOT NULL DEFAULT 'application/json',
              metadata TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gpkg_metadata_reference (
              reference_scope TEXT NOT NULL,
              table_name TEXT,
              column_name TEXT,
              row_id_value INTEGER,
              timestamp DATETIME NOT NULL DEFAULT
                (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              md_file_id INTEGER NOT NULL,
              md_parent_id INTEGER
            );
            """
        )
        cursor = connection.execute(
            "INSERT INTO gpkg_metadata(md_scope, md_standard_uri, mime_type, metadata) "
            "VALUES (?, ?, ?, ?)",
            (
                "dataset",
                "https://mgrb.example/schema/maritime-research-build-1.0",
                "application/json",
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.execute(
            "INSERT INTO gpkg_metadata_reference(reference_scope, md_file_id) "
            "VALUES ('geopackage', ?)",
            (cursor.lastrowid,),
        )


def _copy_base_data(
    root: Path,
    request: ResearchBuildRequest,
    region: Region,
    package_data: Path,
) -> dict:
    base_build_id = request.base_build_id or region.base_build_id or "taiwan-local-canonical"
    source = root / "data" / "derived" / base_build_id
    if not (source / "base.gpkg").exists() or not (source / "bathymetry.tif").exists():
        raise FileNotFoundError(
            f"Cached public base build is missing: {source}. Run the public cartography "
            "acquisition/build first; MGRB will not generate an incomplete basemap."
        )
    shutil.copy2(source / "base.gpkg", package_data / "base.gpkg")
    shutil.copy2(source / "bathymetry.tif", package_data / "bathymetry.tif")
    spec = json.loads((source / "project-spec.json").read_text(encoding="utf-8"))
    return spec


def _filter_observations(
    normalized: gpd.GeoDataFrame,
    request: ResearchBuildRequest,
    region: Region,
) -> gpd.GeoDataFrame:
    timestamps = pd.to_datetime(normalized["timestamp_start"], errors="coerce", utc=True)
    if request.start_date:
        normalized = normalized[timestamps.dt.date >= request.start_date]
        timestamps = timestamps.loc[normalized.index]
    if request.end_date:
        normalized = normalized[timestamps.dt.date <= request.end_date]
    xmin, ymin, xmax, ymax = region.bbox
    longitudes = normalized["longitude"]
    if region.longitude_convention == "360":
        longitudes = longitudes.mod(360.0)
    normalized = normalized[
        longitudes.between(xmin, xmax) & normalized["latitude"].between(ymin, ymax)
    ]
    actors = normalize_actor_names(
        request.actors if request.product_mode else (request.actors or region.default_actors)
    )
    if actors:
        normalized = normalized[normalized["actor_type"].isin(actors)]
    return normalized.copy()


def _public_observations(
    root: Path,
    registry: VesselRegistry,
    request: ResearchBuildRequest,
    region: Region,
) -> gpd.GeoDataFrame:
    seed_path = root / "metadata" / "public-observations-v0.1.csv"
    loaded = pd.read_csv(seed_path, dtype=str, keep_default_na=False)
    normalized = normalize_evidence(
        loaded,
        registry,
        build_id=request.build_id,
        source_type="OFFICIAL_OBSERVATION",
        source_name="MGRB public observation seed v0.1",
        license_text="Government-source derived facts; source terms require review",
        attribution="See source_url and source_name for every observation",
        raw_reference="metadata/public-observations-v0.1.csv",
    )
    normalized["dataset_id"] = "official-observations-seed"
    return _filter_observations(normalized, request, region)


def _orientation_labels(region: Region) -> gpd.GeoDataFrame:
    records = []
    for index, label in enumerate(region.orientation_labels):
        records.append(
            {
                "label_id": f"{region.name}-orientation-{index + 1}",
                "name": str(label["name"]),
                "label_role": str(label.get("role", "place")),
                "paper_visible": int(bool(label.get("paper", True))),
                "media_visible": int(bool(label.get("media", True))),
                "geometry": gpd.points_from_xy(
                    [float(label["longitude"])], [float(label["latitude"])]
                )[0],
            }
        )
    if not records:
        return gpd.GeoDataFrame(
            {
                "label_id": pd.Series(dtype="str"),
                "name": pd.Series(dtype="str"),
                "label_role": pd.Series(dtype="str"),
                "paper_visible": pd.Series(dtype="int"),
                "media_visible": pd.Series(dtype="int"),
            },
            geometry=gpd.GeoSeries([], dtype="geometry", crs=4326),
            crs=4326,
        )
    return gpd.GeoDataFrame(records, geometry="geometry", crs=4326)


def _empty_events() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "event_id": pd.Series(dtype="str"),
            "entity_id": pd.Series(dtype="str"),
            "actor_type": pd.Series(dtype="str"),
            "event_type": pd.Series(dtype="str"),
            "start_time": pd.Series(dtype="str"),
            "end_time": pd.Series(dtype="str"),
            "confidence": pd.Series(dtype="str"),
            "source_type": pd.Series(dtype="str"),
            "source_name": pd.Series(dtype="str"),
        },
        geometry=gpd.GeoSeries([], dtype="geometry", crs=4326),
        crs=4326,
    )


def _filter_events(
    events: gpd.GeoDataFrame,
    region: Region,
    request: ResearchBuildRequest | None = None,
) -> gpd.GeoDataFrame:
    if events.empty:
        return events.copy()
    filtered = events.copy()
    if request is not None:
        time_column = "start_time" if "start_time" in filtered else "timestamp_start"
        timestamps = pd.to_datetime(filtered[time_column], errors="coerce", utc=True)
        if request.start_date:
            filtered = filtered[timestamps.dt.date >= request.start_date]
            timestamps = timestamps.loc[filtered.index]
        if request.end_date:
            filtered = filtered[timestamps.dt.date <= request.end_date]
    xmin, ymin, xmax, ymax = region.bbox
    representative = filtered.geometry.apply(lambda geometry: geometry.representative_point())
    longitude = representative.x
    if region.longitude_convention == "360":
        longitude = longitude.mod(360.0)
    latitude = representative.y
    return filtered[longitude.between(xmin, xmax) & latitude.between(ymin, ymax)].copy()


def _dataset_id(path: Path) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", path.stem.casefold()).strip("-") or "dataset"
    return f"{stem}-{sha256(path)[:10]}"


def _dataset_layer_name(dataset_id: str) -> str:
    return "dataset_" + re.sub(r"[^a-zA-Z0-9_]+", "_", dataset_id)[:50]


def _clip_context(frame: gpd.GeoDataFrame, region: Region) -> gpd.GeoDataFrame:
    if frame.empty:
        return frame.copy()
    representative = frame.to_crs(4326).geometry.apply(
        lambda geometry: geometry.representative_point()
    )
    longitude = representative.x
    xmin, ymin, xmax, ymax = region.bbox
    if region.longitude_convention == "360":
        longitude = longitude.mod(360.0)
    return frame[longitude.between(xmin, xmax) & representative.y.between(ymin, ymax)].copy()


def _empty_maritime_layer() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "source_id": pd.Series(dtype="str"),
            "boundary_type": pd.Series(dtype="str"),
            "legal_status": pd.Series(dtype="str"),
        },
        geometry=gpd.GeoSeries([], dtype="geometry", crs=4326),
        crs=4326,
    )


def _source_license_rows(source_records: list[dict]) -> list[dict[str, object]]:
    rows = []
    for source in source_records:
        rows.append(
            {
                "source_id": source.get("source_id"),
                "provider": source.get("provider"),
                "dataset": source.get("dataset"),
                "license": source.get("license") or source.get("licence"),
                "allowed_use": source.get("allowed_use", "NOT_SPECIFIED"),
                "attribution_required": source.get("attribution_required", True),
                "redistribution_allowed": source.get("redistribution_allowed", "UNKNOWN"),
                "commercial_use_known": source.get("commercial_use_known", False),
                "availability": source.get("availability", "AVAILABLE"),
                "warning": (
                    ""
                    if source.get("commercial_use_known", False)
                    else "COMMERCIAL_USE_REQUIRES_REVIEW"
                ),
            }
        )
    return rows


def prepare_research_package(
    request: ResearchBuildRequest,
    repository_root: Path,
    *,
    marine_adapter: MarineRegionsWFSAdapter | None = None,
) -> PreparedResearchPackage:
    root = repository_root.resolve()
    regions = load_regions(request.regions_config or root / "config" / "regions.yml")
    if request.area not in regions:
        raise ValueError(f"Unknown research area: {request.area}")
    region = regions[request.area]
    if not region.research_preset:
        raise ValueError(f"Region is not a maritime research preset: {request.area}")
    layer_registry = LayerRegistry.load(root / "config" / "data_layers.yml")
    selected_context_records = []
    for layer_id in request.context_layers:
        record = layer_registry.get(layer_id)
        if record.source_class == "REFERENCE_ONLY":
            raise ValueError(f"Reference-only layer cannot be built: {layer_id}")
        selected_context_records.append(record)
    package_dir = (request.output_root / request.build_id).resolve()
    if package_dir.exists():
        raise FileExistsError(f"Research package already exists: {package_dir}")
    directories = {
        name: package_dir / name
        for name in ("project", "data", "raw", "derived", "styles", "exports", "metadata")
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    base_spec = _copy_base_data(root, request, region, directories["data"])
    registry = VesselRegistry.load(
        root / "metadata" / "vessels-v0.1.yml",
        root / "schema" / "vessel_registry.schema.json",
    )
    include_official_observations = (
        request.include_public_observations or "official_observations" in request.context_layers
    )
    observations = (
        _public_observations(root, registry, request, region)
        if include_official_observations
        else gpd.GeoDataFrame()
    )
    public_evidence_records: list[dict] = []
    public_events = _empty_events()
    evidence_source_ids = list(region.public_evidence_sources)
    for layer_id, source_id in (
        ("scsdi_events", ScsdiSouthChinaSeaEventsAdapter.source_id),
        ("pangaea_xue_long_track", PangaeaXueLong2012Adapter.source_id),
    ):
        if layer_id in request.context_layers and source_id not in evidence_source_ids:
            evidence_source_ids.append(source_id)
    for source_id in evidence_source_ids:
        if not request.public_data or not request.live_sources:
            continue
        if source_id == PangaeaXueLong2012Adapter.source_id:
            adapter = PangaeaXueLong2012Adapter()
            cache = adapter.acquire(root / "data" / "raw" / "r2-public")
            loaded = adapter.read(cache)
            normalized_track = normalize_evidence(
                loaded,
                registry,
                build_id=request.build_id,
                source_type="PUBLIC_TRACK",
                source_name="PANGAEA 891818 Xue Long cruise 76XL20120717",
                license_text="CC BY 3.0",
                attribution=("Chen, Cai & Ouyang (2018), PANGAEA, doi:10.1594/PANGAEA.891818"),
                raw_reference=adapter.download_url,
            )
            normalized_track["dataset_id"] = source_id
            normalized_track = _filter_observations(normalized_track, request, region)
            observations = pd.concat([observations, normalized_track], ignore_index=True)
            observations = gpd.GeoDataFrame(observations, geometry="geometry", crs=4326)
            public_evidence_records.append(
                {
                    "source_id": source_id,
                    "provider": "PANGAEA / Third Institute of Oceanography, SOA",
                    "dataset": "Xue Long cruise 76XL20120717 underway track",
                    "version_or_date": "2018-07-02 publication",
                    "original_url": adapter.dataset_url,
                    "download_timestamp_utc": timestamp,
                    "license": "CC BY 3.0",
                    "allowed_use": "research, publication, and redistribution with attribution",
                    "attribution_required": True,
                    "redistribution_allowed": True,
                    "commercial_use_known": True,
                    "spatial_resolution": "3,186 published underway position records",
                    "temporal_coverage": "2012-07-17 through 2012-09-08",
                    "source_sha256": sha256(cache),
                    "availability": "AVAILABLE",
                    "transformations": [
                        "parse PANGAEA tab-delimited dataset",
                        "canonical evidence normalization",
                        "clip to preset area and period",
                        "deterministic track QC and segmentation",
                    ],
                    "normalized_position_count": len(normalized_track),
                    "quality_caveat": "Provider cruise QC flag D",
                }
            )
        elif source_id == ScsdiSouthChinaSeaEventsAdapter.source_id:
            adapter = ScsdiSouthChinaSeaEventsAdapter()
            cache = adapter.acquire(root / "data" / "raw" / "scsdi")
            loaded_events = adapter.read(cache)
            loaded_events["dataset_id"] = source_id
            loaded_events = _filter_events(loaded_events, region, request)
            public_events = gpd.GeoDataFrame(
                pd.concat([public_events, loaded_events], ignore_index=True),
                geometry="geometry",
                crs=4326,
            )
            public_evidence_records.append(
                {
                    "source_id": source_id,
                    "provider": "South China Sea Data Initiative / Harvard Dataverse",
                    "dataset": "South China Sea Data Initiative: News-event Data",
                    "version_or_date": "2.0 (2022-09-08)",
                    "original_url": adapter.dataset_url,
                    "provider_download_url": adapter.download_url,
                    "download_timestamp_utc": timestamp,
                    "license": "CC0 1.0",
                    "allowed_use": "public-domain dedication; attribution retained by MGRB",
                    "attribution_required": False,
                    "redistribution_allowed": True,
                    "commercial_use_known": True,
                    "spatial_resolution": (
                        f"{len(loaded_events)} geolocated records within the research extent"
                    ),
                    "temporal_coverage": "2012 through 2020",
                    "source_sha256": sha256(cache),
                    "availability": "AVAILABLE",
                    "transformations": [
                        "parse provider CSV as Windows-1252",
                        "preserve event identity and location-precision level",
                        "create point geometry from published coordinates",
                        "clip to the South China Sea research extent",
                    ],
                    "normalized_event_count": len(loaded_events),
                    "quality_caveat": (
                        "Event points are not vessel tracks; provider location uncertainty "
                        "levels and radii are retained."
                    ),
                }
            )
        else:
            raise ValueError(f"Unsupported preset public evidence source: {source_id}")
    local_source_records: list[dict] = []
    dataset_manifest_records: list[dict] = []
    user_data_path = directories["data"] / "user-data.gpkg"
    infrastructure_path = directories["data"] / "infrastructure.gpkg"
    infrastructure_frames: list[gpd.GeoDataFrame] = []
    for local_input in request.local_inputs:
        resolved_input = local_input.resolve()
        key = str(local_input)
        resolved_key = str(resolved_input)
        kind = str(
            (request.input_kinds or {}).get(key)
            or (request.input_kinds or {}).get(resolved_key)
            or "TRACK"
        ).upper()
        metadata = dict(
            (request.input_metadata or {}).get(key)
            or (request.input_metadata or {}).get(resolved_key)
            or {}
        )
        dataset_id = _dataset_id(resolved_input)
        field_map = (request.field_maps or {}).get(key) or (request.field_maps or {}).get(
            resolved_key
        )
        source_name = metadata.get("source_name") or resolved_input.name
        license_text = metadata.get("license") or "USER_SUPPLIED_REVIEW_REQUIRED"
        attribution = metadata.get("attribution") or "User-supplied local data"
        source_url = metadata.get("source_url")
        import_summary: object
        record_count = 0
        if kind == "TRACK":
            local, import_summary = normalize_user_input(
                resolved_input,
                build_id=request.build_id,
                field_map=field_map,
            )
            local["dataset_id"] = dataset_id
            local = _filter_observations(local, request, region)
            _write_geodataframe(local, user_data_path, _dataset_layer_name(dataset_id))
            observations = pd.concat([observations, local], ignore_index=True)
            observations = gpd.GeoDataFrame(observations, geometry="geometry", crs=4326)
            record_count = len(local)
            semantic_class = "RAW_POSITION_TRACK"
        elif kind == "OFFICIAL_OBSERVATION":
            local, import_summary = import_official_observations(
                resolved_input,
                build_id=request.build_id,
                field_map=field_map,
                source_name=source_name,
                license_text=license_text,
                attribution=attribution,
            )
            local["dataset_id"] = dataset_id
            local = _filter_observations(local, request, region)
            _write_geodataframe(local, user_data_path, _dataset_layer_name(dataset_id))
            observations = pd.concat([observations, local], ignore_index=True)
            observations = gpd.GeoDataFrame(observations, geometry="geometry", crs=4326)
            record_count = len(local)
            semantic_class = "OFFICIAL_OBSERVATION"
        elif kind == "EVENT":
            local_events, import_summary = import_events(
                resolved_input,
                dataset_id=dataset_id,
                field_map=field_map,
                source_name=source_name,
                source_url=source_url,
                license_text=license_text,
                attribution=attribution,
            )
            local_events = _filter_events(local_events, region, request)
            _write_geodataframe(local_events, user_data_path, _dataset_layer_name(dataset_id))
            public_events = gpd.GeoDataFrame(
                pd.concat([public_events, local_events], ignore_index=True),
                geometry="geometry",
                crs=4326,
            )
            record_count = len(local_events)
            semantic_class = "EVENT_GEOMETRY"
        elif kind in {
            "PORT",
            "CABLE_LANDING_POINT",
            "SUBMARINE_CABLE",
            "OTHER_INFRASTRUCTURE",
        }:
            source_class = metadata.get("source_class") or "BYO_LICENSED"
            layer_kind = "OTHER" if kind == "OTHER_INFRASTRUCTURE" else kind
            infrastructure, import_summary = import_infrastructure(
                resolved_input,
                layer_kind=layer_kind,
                source_class=source_class,
                source_name=source_name,
                license_text=license_text,
                attribution=attribution,
                redistribution=metadata.get("redistribution") or "DISABLED_PENDING_REVIEW",
            )
            infrastructure["dataset_id"] = dataset_id
            infrastructure = _clip_context(infrastructure, region)
            _write_geodataframe(infrastructure, user_data_path, _dataset_layer_name(dataset_id))
            infrastructure_frames.append(infrastructure)
            record_count = len(infrastructure)
            semantic_class = "INFRASTRUCTURE_CONTEXT"
        else:
            raise ValueError(f"Unsupported input kind: {kind}")
        summary_payload = (
            import_summary.to_dict() if hasattr(import_summary, "to_dict") else import_summary
        )
        dataset_manifest_records.append(
            {
                "dataset_id": dataset_id,
                "filename": resolved_input.name,
                "input_kind": kind,
                "semantic_class": semantic_class,
                "independent_layer": _dataset_layer_name(dataset_id),
                "record_count_after_filters": record_count,
                "source_sha256": sha256(resolved_input),
                "source_name": source_name,
                "source_url": source_url,
                "license": license_text,
                "attribution": attribution,
                "import_qc": summary_payload,
            }
        )
        local_source_records.append(
            {
                "source_id": f"local-{sha256(resolved_input)[:12]}",
                "provider": "User supplied",
                "dataset": resolved_input.name,
                "version_or_date": None,
                "original_url": source_url,
                "license": license_text,
                "allowed_use": "local processing only until reviewed",
                "attribution_required": True,
                "redistribution_allowed": False,
                "commercial_use_known": False,
                "spatial_resolution": None,
                "temporal_coverage": None,
                "source_sha256": sha256(resolved_input),
                "availability": "LOCAL_ONLY",
                "evidence_context_type": semantic_class,
                "transformations": [
                    "local import",
                    "semantic-class-preserving normalization",
                    "independent dataset layer",
                    "research extent and time filter where applicable",
                ],
                "import_qc": summary_payload,
            }
        )
    qc = quality_control(observations, QualityControlConfig())
    coverage_metrics = track_coverage_metrics(
        qc.cleaned_points,
        requested_start=request.start_date,
        requested_end=request.end_date,
    )
    if not coverage_metrics.empty:
        geometry_name = qc.cleaned_points.geometry.name
        qc.cleaned_points = gpd.GeoDataFrame(
            qc.cleaned_points.merge(
                coverage_metrics,
                on=["dataset_id", "entity_id"],
                how="left",
                suffixes=("", "_coverage"),
            ),
            geometry=geometry_name,
            crs=4326,
        )
        if not qc.track_segments.empty:
            qc.track_segments = gpd.GeoDataFrame(
                qc.track_segments.merge(
                    coverage_metrics,
                    on=["dataset_id", "entity_id"],
                    how="left",
                    suffixes=("", "_coverage"),
                ),
                geometry="geometry",
                crs=4326,
            )

    observations_path = directories["data"] / "observations.gpkg"
    tracks_path = directories["data"] / "tracks.gpkg"
    events_path = directories["data"] / "events.gpkg"
    context_path = directories["data"] / "context.gpkg"
    vessels_path = directories["data"] / "vessels.gpkg"
    maritime_path = directories["data"] / "maritime.gpkg"
    _write_geodataframe(qc.cleaned_points, observations_path, "observations")
    _write_geodataframe(qc.track_segments, tracks_path, "track_segments")
    _write_geodataframe(public_events, events_path, "events")
    _write_geodataframe(_orientation_labels(region), context_path, "orientation_labels")

    entity_ids = set(qc.cleaned_points["entity_id"].dropna().astype(str))
    registry_records = registry.subset(entity_ids)
    registry_frame = pd.DataFrame(registry_records)
    if registry_frame.empty and not len(registry_frame.columns):
        registry_frame = pd.DataFrame({"entity_id": pd.Series(dtype="str")})
    for column in ("aliases", "former_names", "source_refs"):
        if column in registry_frame:
            registry_frame[column] = registry_frame[column].map(json.dumps)
    _write_nonspatial(registry_frame, vessels_path, "vessel_registry")

    source_warnings: list[str] = []
    if region.public_evidence_sources and (not request.public_data or not request.live_sources):
        source_warnings.append(
            "Preset public evidence unavailable: offline/public-data-disabled mode"
        )
    marine_records: list[dict] = []
    if request.public_data and request.live_sources:
        adapter = marine_adapter or MarineRegionsWFSAdapter()
        marine_bbox = buffered_vector_bbox(region.bbox, region.longitude_convention, region.profile)
        if region.longitude_convention == "360" and marine_bbox[2] > 180.0:
            # Marine Regions WFS accepts canonical WGS84 longitudes. The tiny
            # 179..180 continuation is supplied by the portable public base;
            # request the contiguous western-hemisphere portion here.
            marine_bbox = (
                max(-180.0, marine_bbox[0] - 360.0),
                marine_bbox[1],
                marine_bbox[2] - 360.0,
                marine_bbox[3],
            )
        marine_layers, marine_records = adapter.fetch(
            marine_bbox,
            root / "data" / "raw" / "marine_regions" / request.area,
        )
    else:
        marine_layers = {name: _empty_maritime_layer() for name in MarineRegionsWFSAdapter.layers}
        source_warnings.append("Marine Regions unavailable: offline/public-data-disabled mode")
        for name, (_, source_id) in MarineRegionsWFSAdapter.layers.items():
            marine_records.append(
                {
                    "source_id": source_id,
                    "provider": "Flanders Marine Institute (VLIZ), Marine Regions",
                    "dataset": name,
                    "license": "CC BY 4.0",
                    "allowed_use": "research and redistribution with attribution",
                    "attribution_required": True,
                    "redistribution_allowed": True,
                    "commercial_use_known": True,
                    "availability": "UNAVAILABLE_OFFLINE_MODE",
                    "transformations": [],
                }
            )
    for optional_layer in (
        "maritime_boundary",
        "continental_shelf",
        "computed_median",
        "custom_boundary",
    ):
        marine_layers.setdefault(optional_layer, _empty_maritime_layer())
        if optional_layer in request.enabled_maritime_layers:
            source_warnings.append(
                f"{optional_layer} selected but no source or computation input was supplied"
            )
    for layer_name, frame in marine_layers.items():
        _write_geodataframe(frame, maritime_path, layer_name)

    context_source_records: list[dict] = []
    if "nga_world_port_index" in request.context_layers:
        wpi_adapter = WorldPortIndexAdapter()
        wpi_source = wpi_adapter.acquire(root / "data" / "raw" / "nga_world_port_index")
        ports = _clip_context(wpi_adapter.read(wpi_source), region)
        ports["dataset_id"] = "nga-world-port-index"
        ports["infrastructure_kind"] = "PORT"
        ports["source_class"] = "OPEN"
        ports["license"] = "United States government publication; provider notices retained"
        ports["attribution"] = "National Geospatial-Intelligence Agency, World Port Index"
        ports["redistribution"] = "REVIEW_PROVIDER_NOTICES"
        infrastructure_frames.append(ports)
        context_source_records.append(wpi_adapter.source_record(wpi_source, len(ports)))
    if infrastructure_frames:
        infrastructure_all = gpd.GeoDataFrame(
            pd.concat(infrastructure_frames, ignore_index=True), geometry="geometry", crs=4326
        )
        for kind, layer_name in (
            ("PORT", "ports"),
            ("CABLE_LANDING_POINT", "cable_landing_points"),
            ("SUBMARINE_CABLE", "submarine_cables"),
            ("OTHER", "other_infrastructure"),
        ):
            selected = infrastructure_all[infrastructure_all["infrastructure_kind"].eq(kind)].copy()
            if not selected.empty:
                _write_geodataframe(selected, infrastructure_path, layer_name)

    traffic_available = False
    traffic_details: dict[str, object] = {}
    traffic_input = request.traffic_density
    cached_traffic = root / "data" / "raw" / "r2-public" / "shipdensity_global.zip"
    if (
        traffic_input is None
        and "world_bank_shipping_density" in request.context_layers
        and cached_traffic.exists()
    ):
        traffic_input = cached_traffic
    if traffic_input:
        traffic_window = buffered_bbox(region.bbox, region.longitude_convention, region.profile)
        traffic_details = WorldBankTrafficDensityAdapter().subset(
            traffic_input,
            traffic_window,
            directories["data"] / "normal-traffic-density.tif",
            buffer_degrees=1.0,
        )
        traffic_available = True
    else:
        source_warnings.append(
            "World Bank traffic density not cached; explicit empty availability group retained"
        )
    if "osm_submarine_cables" in request.context_layers and not any(
        record["input_kind"] in {"SUBMARINE_CABLE", "CABLE_LANDING_POINT"}
        for record in dataset_manifest_records
    ):
        source_warnings.append(
            "OSM submarine infrastructure selected but no audited OSM extract was supplied; "
            "no geometry was fabricated or scraped"
        )
    if "byo_cable_layer" in request.context_layers and not any(
        record["input_kind"] in {"SUBMARINE_CABLE", "CABLE_LANDING_POINT"}
        for record in dataset_manifest_records
    ):
        source_warnings.append(
            "BYO cable context selected but no licensed local cable input was supplied"
        )

    coverage_metrics.to_csv(directories["derived"] / "track_coverage.csv", index=False)
    eez_frame = marine_layers.get("eez_reference", _empty_maritime_layer())
    crossing_candidates = zone_crossing_candidates(qc.track_segments, eez_frame)
    eez_boundaries = eez_frame.copy()
    if not eez_boundaries.empty:
        eez_boundaries["geometry"] = eez_boundaries.geometry.boundary
    boundary_distances = distance_to_features(
        qc.cleaned_points,
        eez_boundaries,
        distance_name="distance_to_eez_boundary_m",
    )
    if infrastructure_frames:
        ports_for_distance = gpd.GeoDataFrame(
            pd.concat(infrastructure_frames, ignore_index=True), geometry="geometry", crs=4326
        )
        ports_for_distance = ports_for_distance[
            ports_for_distance["infrastructure_kind"].eq("PORT")
        ]
    else:
        ports_for_distance = gpd.GeoDataFrame(geometry=[], crs=4326)
    port_distances = distance_to_features(
        qc.cleaned_points,
        ports_for_distance,
        distance_name="distance_to_port_m",
    )
    repeated_visits = repeated_area_visits(qc.cleaned_points, eez_frame)
    slow_candidates = low_speed_candidates(qc.cleaned_points)
    analytics_path = directories["derived"] / "analytics.gpkg"
    if not crossing_candidates.empty:
        _write_geodataframe(crossing_candidates, analytics_path, "eez_crossing_candidates")
    for name, frame in (
        ("eez_crossing_candidates.csv", crossing_candidates.drop(columns="geometry")),
        ("distance_to_eez_boundary.csv", boundary_distances),
        ("distance_to_port.csv", port_distances),
        ("repeated_area_visits.csv", repeated_visits),
        ("low_speed_candidates.csv", slow_candidates),
    ):
        frame.to_csv(directories["derived"] / name, index=False)
    analytics_manifest = {
        "schema": "mgrb-transparent-analytics-1.1",
        "build_id": request.build_id,
        "metrics": {
            "track_coverage": {
                "rows": len(coverage_metrics),
                "semantics": "descriptive observation completeness and gap statistics",
            },
            "eez_crossing_candidates": {
                "rows": len(crossing_candidates),
                "semantics": "geometric intersections with sourced reference EEZ boundaries; "
                "not a legal determination",
            },
            "distance_to_eez_boundary": {
                "rows": len(boundary_distances),
                "semantics": "planar metric distance in an automatically estimated local CRS",
            },
            "distance_to_port": {
                "rows": len(port_distances),
                "semantics": "descriptive nearest-feature distance; port data are general context",
            },
            "repeated_area_visits": {
                "rows": len(repeated_visits),
                "semantics": "descriptive point presence transitions, not intent",
            },
            "low_speed_candidates": {
                "rows": len(slow_candidates),
                "semantics": "threshold candidates only, not behavior classification",
            },
        },
        "prohibited_inferences": [
            "espionage",
            "surveillance",
            "militia status",
            "hostile intent",
            "deliberate AIS disablement",
        ],
    }
    analytics_manifest_path = directories["metadata"] / "analytics-manifest.json"
    analytics_manifest_path.write_text(
        json.dumps(analytics_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    dataset_manifest = {
        "schema": "mgrb-dataset-manifest-1.1",
        "build_id": request.build_id,
        "time_filter": {
            "start": request.start_date.isoformat() if request.start_date else None,
            "end": request.end_date.isoformat() if request.end_date else None,
        },
        "datasets": dataset_manifest_records,
        "independence_rule": (
            "Every local input has an independent dataset_id and GeoPackage layer; event and "
            "infrastructure semantics are never promoted to vessel positions."
        ),
    }
    dataset_manifest_path = directories["metadata"] / "dataset-manifest.json"
    dataset_manifest_path.write_text(
        json.dumps(dataset_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for name, frame in (
        ("cleaned_points.csv", qc.cleaned_points.drop(columns="geometry")),
        ("excluded_points.csv", qc.excluded_points.drop(columns="geometry")),
        ("quality_flags.csv", qc.quality_flags),
        ("gaps.csv", qc.gaps),
        ("track_summary.csv", qc.track_segments.drop(columns="geometry")),
        ("vessel_summary.csv", qc.vessel_summary),
    ):
        frame.to_csv(directories["derived"] / name, index=False)
    source_evidence = qc.cleaned_points.reindex(
        columns=[
            "observation_id",
            "dataset_id",
            "entity_id",
            "source_type",
            "source_name",
            "source_record_id",
            "source_url",
            "source_date",
            "observation_method",
            "position_uncertainty_m",
            "temporal_uncertainty_s",
            "license",
            "attribution",
        ]
    )
    source_evidence.to_csv(directories["derived"] / "source_evidence.csv", index=False)

    source_registry = SourceRegistry.load(root / "metadata" / "sources.yml")
    source_records = list(base_spec["sources"])
    if include_official_observations:
        seed_hash = sha256(root / "metadata" / "public-observations-v0.1.csv")
        for source_id in (
            "japan_joint_staff_public_observations",
            "japan_mofa_jcg_public_observations",
            "taiwan_cga_public_observations",
        ):
            record = source_registry.get(source_id).manifest_record(
                ["official_observations", "inferred_connections"],
                [
                    "normalize source-described positions",
                    "preserve uncertainty",
                    "clip to area/period",
                ],
                downloaded_at_utc=None,
                source_hash=None,
            )
            record["normalized_fixture_sha256"] = seed_hash
            source_records.append(record)
    source_records.extend(marine_records)
    source_records.extend(public_evidence_records)
    source_records.extend(local_source_records)
    source_records.extend(context_source_records)
    for record in selected_context_records:
        source_records.append(
            {
                "source_id": f"layer-registry:{record.layer_id}",
                **record.to_dict(),
                "availability": (
                    "AVAILABLE"
                    if record.layer_id == "nga_world_port_index" and infrastructure_path.exists()
                    else "AVAILABLE"
                    if record.layer_id == "world_bank_shipping_density" and traffic_available
                    else "SELECTED_WITH_IMPORT_REQUIRED"
                    if record.connector_status == "IMPORT_ONLY"
                    else "SELECTED_REGISTRY_RECORD",
                ),
            }
        )
    traffic_record = source_registry.get("world_bank_shipping_density_2021").manifest_record(
        ["normal_traffic_density"],
        ["clip to research area"] if traffic_available else [],
        downloaded_at_utc=timestamp if traffic_available else None,
        source_hash=str(traffic_details.get("source_sha256")) if traffic_available else None,
        availability="AVAILABLE" if traffic_available else "NOT_CACHED_LARGE_SOURCE",
    )
    if traffic_available:
        traffic_record.update(
            {
                "provider_download_url": WorldBankTrafficDensityAdapter.download_url,
                "source_archive_bytes": traffic_input.stat().st_size,
                "subset_sha256": traffic_details["subset_sha256"],
                "subset_bbox": traffic_details["subset_bbox"],
                "density_transform": traffic_details["transform"],
            }
        )
    source_records.append(traffic_record)

    source_manifest = {
        "schema": "mgrb-source-manifest-1.1",
        "manifest_id": f"{request.build_id}-sources",
        "selected_context_layers": list(request.context_layers),
        "sources": source_records,
        "warnings": source_warnings,
    }
    source_manifest_path = directories["metadata"] / "mgrb-source-manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copy2(source_manifest_path, directories["metadata"] / "source_manifest.json")

    background_config = BACKGROUND_PRESETS.get(request.background)
    if background_config is None:
        raise ValueError(f"Unknown background preset: {request.background}")
    theme = resolve_theme(str(background_config["theme"]), root / "config" / "themes")
    style_manifest = theme.manifest()
    style_manifest.update(
        {
            "mgrb_version": __version__,
            "cartographic_profile": region.profile,
            "layout_profile": "research-paper-adaptive",
            "track_semantics": {
                "OBSERVED_TRACK": "solid",
                "SHORT_INTERPOLATION": "short dash",
                "INFERRED_CONNECTION": "long dash",
                "OFFICIAL_OBSERVATION": "square marker",
                "UNCERTAIN_DETECTION": "halo marker",
            },
            "actor_palette": {
                "PLAN": "#9e2f2f",
                "CCG": "#d07823",
                "RESEARCH_SURVEY": "#6d3d8f",
                "FISHING": "#237a57",
                "MARITIME_MILITIA": "#333333",
            },
            "confidence_is_not_color_only": True,
        }
    )
    style_path = directories["metadata"] / "mgrb-style-manifest.json"
    style_path.write_text(
        json.dumps(style_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    profiles = load_profiles(root / "config" / "profiles.yml")
    layouts = load_yaml(root / "config" / "layouts.yml")["layouts"]
    layout = resolve_layout_geometry(region.bbox, layouts[profiles[region.profile].layout])
    commit = git_commit(root)
    product = load_yaml(root / "config" / "product.yml")["product"]
    build_manifest = {
        "schema": "mgrb-maritime-research-build-1.0",
        "mgrb_version": __version__,
        "formal_name": product["formal_name"],
        "canonical_repository": product.get("canonical_repository"),
        "release_persistent_identifier": product.get("release_persistent_identifier"),
        "canonical_release": {
            "manifest_url": product.get("release_manifest_url"),
            "manifest_sha256": product.get("release_manifest_sha256"),
            "signature_url": product.get("release_signature_url"),
        },
        "git_commit": commit,
        "build_id": request.build_id,
        "build_timestamp_utc": timestamp,
        "region_profile": region.name,
        "cartographic_profile": region.profile,
        "layout_profile": "research-paper-adaptive",
        "layout_orientation": layout["orientation"],
        "page_mm": layout["page_mm"],
        "map_mm": layout["map_mm"],
        "crs": region.display_crs,
        "bbox_epsg4326": list(region.bbox),
        "background": request.background,
        "enabled_maritime_layers": list(request.enabled_maritime_layers),
        "enabled_context_layers": list(request.context_layers),
        "product_mode": request.product_mode,
        "visible_footer": request.visible_footer,
        "requested_outputs": list(request.requested_outputs),
        "research_period": {
            "from": request.start_date.isoformat() if request.start_date else None,
            "to": request.end_date.isoformat() if request.end_date else None,
        },
        "actors": list(
            normalize_actor_names(
                request.actors
                if request.product_mode
                else (request.actors or region.default_actors)
            )
        ),
        "source_manifest_id": source_manifest["manifest_id"],
        "source_manifest_sha256": sha256(source_manifest_path),
        "theme": {
            "palette_id": theme.palette_id,
            "palette_origin": theme.origin,
            "palette_sha256": theme.sha256,
            "style_overrides": theme.style_overrides,
        },
        "evidence": {
            "cleaned_observations": len(qc.cleaned_points),
            "excluded_observations": len(qc.excluded_points),
            "quality_flags": len(qc.quality_flags),
            "track_segments": len(qc.track_segments),
            "segment_types": qc.track_segments["segment_type"].value_counts().to_dict(),
            "actor_observation_counts": qc.cleaned_points["actor_type"].value_counts().to_dict(),
            "actor_segment_counts": {
                f"{actor}:{segment_type}": int(count)
                for (actor, segment_type), count in qc.track_segments.groupby(
                    ["actor_type", "segment_type"]
                )
                .size()
                .items()
            },
            "evidence_methods": qc.cleaned_points["observation_method"].value_counts().to_dict(),
            "public_events": len(public_events),
            "public_event_types": public_events["event_type"].value_counts().to_dict(),
            "independent_local_datasets": len(dataset_manifest_records),
            "dataset_semantic_classes": {
                record["dataset_id"]: record["semantic_class"]
                for record in dataset_manifest_records
            },
            "track_coverage": json.loads(coverage_metrics.to_json(orient="records")),
            "transparent_analytics": analytics_manifest["metrics"],
            "inferred_entity_integrity": True,
        },
        "restricted_raw_data_included": False,
        "source_warnings": source_warnings,
        "recommended_citation": (
            f"Maritime Geospatial Research Base (MGRB), version {__version__}, maritime "
            f"research build {request.build_id}, Git commit {commit or 'unknown'}. Cite each "
            "public observation and geospatial source listed in the source manifest."
        ),
    }
    build_manifest_path = directories["metadata"] / "mgrb-build.json"
    build_manifest_path.write_text(
        json.dumps(build_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copy2(build_manifest_path, directories["metadata"] / "build_manifest.json")

    license_rows = _source_license_rows(source_records)
    with (directories["metadata"] / "license_manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(license_rows[0]))
        writer.writeheader()
        writer.writerows(license_rows)

    provenance = {
        "schema": "mgrb-maritime-provenance-1.0",
        "build": build_manifest,
        "processing": [
            "resolve research area defaults",
            "reuse buffered public cartographic base",
            "acquire and clip Marine Regions reference zones when enabled",
            "normalize source-backed vessel observations",
            "resolve vessel identities without behavioral attribution",
            "run deterministic position/time/identity quality control",
            "segment dense AIS or documented public cruise tracks only as observed tracks",
            "represent sparse official-observation links only as inferred connections",
            "organize portable QGIS research package",
        ],
        "raw_data_policy": "Restricted and BYO raw files are excluded by default",
    }
    (directories["metadata"] / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (directories["raw"] / "README.md").write_text(
        "# Raw evidence\n\nNo raw evidence files are included. Public observations are "
        "represented as normalized factual records with source URLs. Restricted/BYO raw "
        "files remain local and are excluded from distributable packages by default.\n",
        encoding="utf-8",
    )
    product_spec_path = directories["metadata"] / "product-build-spec.json"
    product_spec_path.write_text(
        json.dumps(
            {
                "schema": "mgrb-product-build-spec-1.0",
                "area": region.name,
                "extent": list(region.bbox),
                "projection": region.display_crs,
                "cartographic_profile": region.profile,
                "background": request.background,
                "maritime_layers": list(request.enabled_maritime_layers),
                "context_layers": list(request.context_layers),
                "input_datasets": [
                    {
                        "filename": path.name,
                        "sha256": sha256(path),
                        "input_kind": (request.input_kinds or {}).get(str(path), "TRACK"),
                    }
                    for path in request.local_inputs
                ],
                "field_maps": {
                    Path(path).name: mapping for path, mapping in (request.field_maps or {}).items()
                },
                "include_public_observations": include_official_observations,
                "visible_footer": request.visible_footer,
                "requested_outputs": list(request.requested_outputs),
                "product_mode": request.product_mode,
                "start_date": request.start_date.isoformat() if request.start_date else None,
                "end_date": request.end_date.isoformat() if request.end_date else None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (directories["metadata"] / "README.md").write_text(
        (
            f"# {region.title or region.purpose}\n\n"
            f"MGRB maritime research build `{request.build_id}`. Open the QGIS project in "
            "`../project/`; all ordinary data paths are relative to this package.\n\n"
            "## Evidence semantics\n\n"
            "Solid lines are dense observed tracks. Dashed lines are inferred connections "
            "between sparse observations and are not observed routes. Square points are "
            "official observations. Halo markers indicate lower positional confidence.\n\n"
            "## Source and legal caution\n\n"
            "Maritime zones are sourced reference features, not self-authenticating legal "
            "boundaries. Consult `license_manifest.csv`, `mgrb-source-manifest.json`, and "
            "`provenance.json` before redistribution or publication. User-supplied and "
            "licensed raw files are excluded by default.\n\n"
            f"Recommended citation: {build_manifest['recommended_citation']}\n"
        ),
        encoding="utf-8",
    )

    spec = {
        "schema": "mgrb-maritime-qgis-spec-1.0",
        "build": build_manifest,
        "region": asdict(region),
        "cartographic_profile": asdict(profiles[region.profile]),
        "layout": layout,
        "theme": style_manifest,
        "source_warnings": source_warnings,
        "availability": {
            "marine_regions": all(
                not marine_layers[name].empty for name in MarineRegionsWFSAdapter.layers
            ),
            "normal_traffic_density": traffic_available,
            "infrastructure": infrastructure_path.exists(),
            "analytics": analytics_path.exists(),
        },
        "selected_state": {
            "background": request.background,
            "maritime_layers": list(request.enabled_maritime_layers),
            "context_layers": list(request.context_layers),
            "time_filter": {
                "start": request.start_date.isoformat() if request.start_date else None,
                "end": request.end_date.isoformat() if request.end_date else None,
            },
            "product_mode": request.product_mode,
        },
        "files": {
            "base_gpkg": "data/base.gpkg",
            "maritime_gpkg": "data/maritime.gpkg",
            "vessels_gpkg": "data/vessels.gpkg",
            "observations_gpkg": "data/observations.gpkg",
            "tracks_gpkg": "data/tracks.gpkg",
            "events_gpkg": "data/events.gpkg",
            "context_gpkg": "data/context.gpkg",
            "user_data_gpkg": "data/user-data.gpkg" if user_data_path.exists() else None,
            "infrastructure_gpkg": (
                "data/infrastructure.gpkg" if infrastructure_path.exists() else None
            ),
            "analytics_gpkg": "derived/analytics.gpkg" if analytics_path.exists() else None,
            "bathymetry": "data/bathymetry.tif",
            "traffic_density": ("data/normal-traffic-density.tif" if traffic_available else None),
            "build_manifest": "metadata/mgrb-build.json",
            "source_manifest": "metadata/mgrb-source-manifest.json",
            "style_manifest": "metadata/mgrb-style-manifest.json",
            "product_build_spec": "metadata/product-build-spec.json",
            "dataset_manifest": "metadata/dataset-manifest.json",
            "analytics_manifest": "metadata/analytics-manifest.json",
        },
    }
    spec_path = directories["metadata"] / "research-spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    metadata_payload = {
        "formal_name": build_manifest["formal_name"],
        "mgrb_version": __version__,
        "git_commit": commit,
        "build_id": request.build_id,
        "region": region.name,
        "source_manifest_sha256": build_manifest["source_manifest_sha256"],
        "recommended_citation": build_manifest["recommended_citation"],
    }
    for gpkg in (
        directories["data"] / "base.gpkg",
        maritime_path,
        vessels_path,
        observations_path,
        tracks_path,
        events_path,
        context_path,
        user_data_path,
        infrastructure_path,
        analytics_path,
    ):
        _embed_gpkg_metadata(gpkg, metadata_payload)
    with rasterio.open(directories["data"] / "bathymetry.tif", "r+") as dataset:
        dataset.update_tags(
            MGRB_VERSION=__version__,
            MGRB_BUILD_ID=request.build_id,
            MGRB_GIT_COMMIT=commit or "unknown",
            MGRB_SOURCE_MANIFEST_SHA256=build_manifest["source_manifest_sha256"],
            MGRB_RECOMMENDED_CITATION=build_manifest["recommended_citation"],
        )
    if traffic_available:
        with rasterio.open(directories["data"] / "normal-traffic-density.tif", "r+") as dataset:
            dataset.update_tags(
                MGRB_VERSION=__version__,
                MGRB_BUILD_ID=request.build_id,
                MGRB_GIT_COMMIT=commit or "unknown",
                MGRB_SOURCE_MANIFEST_SHA256=build_manifest["source_manifest_sha256"],
            )
    return PreparedResearchPackage(
        request.build_id,
        package_dir,
        spec_path,
        len(qc.cleaned_points),
        len(qc.track_segments),
        tuple(source_warnings),
    )
