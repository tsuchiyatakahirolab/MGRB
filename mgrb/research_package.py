from __future__ import annotations

import csv
import json
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
    WorldBankTrafficDensityAdapter,
)
from .cartography import buffered_bbox, buffered_vector_bbox, resolve_layout_geometry
from .config import Region, load_profiles, load_regions, load_yaml
from .evidence import QualityControlConfig, normalize_evidence, quality_control, read_evidence
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
        longitudes.between(xmin, xmax)
        & normalized["latitude"].between(ymin, ymax)
    ]
    actors = normalize_actor_names(request.actors or region.default_actors)
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
    regions = load_regions(root / "config" / "regions.yml")
    if request.area not in regions:
        raise ValueError(f"Unknown research area: {request.area}")
    region = regions[request.area]
    if not region.research_preset:
        raise ValueError(f"Region is not a maritime research preset: {request.area}")
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
    observations = _public_observations(root, registry, request, region)
    public_track_records: list[dict] = []
    for source_id in region.public_evidence_sources:
        if source_id != PangaeaXueLong2012Adapter.source_id:
            raise ValueError(f"Unsupported preset public evidence source: {source_id}")
        if not request.public_data or not request.live_sources:
            continue
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
            attribution=(
                "Chen, Cai & Ouyang (2018), PANGAEA, "
                "doi:10.1594/PANGAEA.891818"
            ),
            raw_reference=adapter.download_url,
        )
        normalized_track = _filter_observations(normalized_track, request, region)
        observations = pd.concat([observations, normalized_track], ignore_index=True)
        observations = gpd.GeoDataFrame(observations, geometry="geometry", crs=4326)
        public_track_records.append(
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
    local_source_records: list[dict] = []
    for local_input in request.local_inputs:
        local = read_evidence(
            local_input,
            registry,
            build_id=request.build_id,
            source_type="USER_SUPPLIED",
            license_text="USER_SUPPLIED_REVIEW_REQUIRED",
            attribution="User-supplied local evidence",
        )
        observations = pd.concat([observations, local], ignore_index=True)
        observations = gpd.GeoDataFrame(observations, geometry="geometry", crs=4326)
        local_source_records.append(
            {
                "source_id": f"local-{sha256(local_input)[:12]}",
                "provider": "User supplied",
                "dataset": local_input.name,
                "version_or_date": None,
                "original_url": None,
                "license": "USER_SUPPLIED_REVIEW_REQUIRED",
                "allowed_use": "local processing only until reviewed",
                "attribution_required": True,
                "redistribution_allowed": False,
                "commercial_use_known": False,
                "spatial_resolution": None,
                "temporal_coverage": None,
                "source_sha256": sha256(local_input),
                "availability": "LOCAL_ONLY",
                "transformations": ["local import", "canonical normalization"],
            }
        )
    qc = quality_control(observations, QualityControlConfig())

    observations_path = directories["data"] / "observations.gpkg"
    tracks_path = directories["data"] / "tracks.gpkg"
    events_path = directories["data"] / "events.gpkg"
    context_path = directories["data"] / "context.gpkg"
    vessels_path = directories["data"] / "vessels.gpkg"
    maritime_path = directories["data"] / "maritime.gpkg"
    _write_geodataframe(qc.cleaned_points, observations_path, "observations")
    _write_geodataframe(qc.track_segments, tracks_path, "track_segments")
    _write_geodataframe(_empty_events(), events_path, "events")
    _write_geodataframe(_orientation_labels(region), context_path, "orientation_labels")

    entity_ids = set(qc.cleaned_points["entity_id"].dropna().astype(str))
    registry_records = registry.subset(entity_ids)
    registry_frame = pd.DataFrame(registry_records)
    for column in ("aliases", "former_names", "source_refs"):
        if column in registry_frame:
            registry_frame[column] = registry_frame[column].map(json.dumps)
    _write_nonspatial(registry_frame, vessels_path, "vessel_registry")

    source_warnings: list[str] = []
    if region.public_evidence_sources and (not request.public_data or not request.live_sources):
        source_warnings.append(
            "Preset public track unavailable: offline/public-data-disabled mode"
        )
    marine_records: list[dict] = []
    if request.public_data and request.live_sources:
        adapter = marine_adapter or MarineRegionsWFSAdapter()
        marine_bbox = buffered_vector_bbox(
            region.bbox, region.longitude_convention, region.profile
        )
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
        marine_layers = {
            name: _empty_maritime_layer() for name in MarineRegionsWFSAdapter.layers
        }
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
    for layer_name, frame in marine_layers.items():
        _write_geodataframe(frame, maritime_path, layer_name)

    traffic_available = False
    traffic_details: dict[str, object] = {}
    if request.traffic_density:
        traffic_window = buffered_bbox(
            region.bbox, region.longitude_convention, region.profile
        )
        traffic_details = WorldBankTrafficDensityAdapter().subset(
            request.traffic_density,
            traffic_window,
            directories["data"] / "normal-traffic-density.tif",
            buffer_degrees=1.0,
        )
        traffic_available = True
    else:
        source_warnings.append(
            "World Bank traffic density not cached; explicit empty availability group retained"
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
    source_evidence = qc.cleaned_points[
        [
            "observation_id",
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
    ]
    source_evidence.to_csv(directories["derived"] / "source_evidence.csv", index=False)

    source_registry = SourceRegistry.load(root / "metadata" / "sources.yml")
    source_records = list(base_spec["sources"])
    seed_hash = sha256(root / "metadata" / "public-observations-v0.1.csv")
    for source_id in (
        "japan_joint_staff_public_observations",
        "japan_mofa_jcg_public_observations",
        "taiwan_cga_public_observations",
    ):
        record = source_registry.get(source_id).manifest_record(
            ["official_observations", "inferred_connections"],
            ["normalize source-described positions", "preserve uncertainty", "clip to area/period"],
            downloaded_at_utc=None,
            source_hash=None,
        )
        record["normalized_fixture_sha256"] = seed_hash
        source_records.append(record)
    source_records.extend(marine_records)
    source_records.extend(public_track_records)
    source_records.extend(local_source_records)
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
                "source_archive_bytes": request.traffic_density.stat().st_size,
                "subset_sha256": traffic_details["subset_sha256"],
                "subset_bbox": traffic_details["subset_bbox"],
                "density_transform": traffic_details["transform"],
            }
        )
    source_records.append(traffic_record)

    source_manifest = {
        "schema": "mgrb-source-manifest-1.1",
        "manifest_id": f"{request.build_id}-sources",
        "sources": source_records,
        "warnings": source_warnings,
    }
    source_manifest_path = directories["metadata"] / "mgrb-source-manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copy2(source_manifest_path, directories["metadata"] / "source_manifest.json")

    theme = resolve_theme("overlay-quiet", root / "config" / "themes")
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
        "research_period": {
            "from": request.start_date.isoformat() if request.start_date else None,
            "to": request.end_date.isoformat() if request.end_date else None,
        },
        "actors": list(normalize_actor_names(request.actors or region.default_actors)),
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
                ).size().items()
            },
            "evidence_methods": qc.cleaned_points["observation_method"].value_counts().to_dict(),
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
            "marine_regions": all(not frame.empty for frame in marine_layers.values()),
            "normal_traffic_density": traffic_available,
        },
        "files": {
            "base_gpkg": "data/base.gpkg",
            "maritime_gpkg": "data/maritime.gpkg",
            "vessels_gpkg": "data/vessels.gpkg",
            "observations_gpkg": "data/observations.gpkg",
            "tracks_gpkg": "data/tracks.gpkg",
            "events_gpkg": "data/events.gpkg",
            "context_gpkg": "data/context.gpkg",
            "bathymetry": "data/bathymetry.tif",
            "traffic_density": (
                "data/normal-traffic-density.tif" if traffic_available else None
            ),
            "build_manifest": "metadata/mgrb-build.json",
            "source_manifest": "metadata/mgrb-source-manifest.json",
            "style_manifest": "metadata/mgrb-style-manifest.json",
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
