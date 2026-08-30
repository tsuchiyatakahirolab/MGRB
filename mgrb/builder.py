from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd

from . import __version__
from .cartography import resolve_layout_geometry
from .config import Region
from .provenance import git_commit, sha256
from .raster import clip_raster, clip_raster_360
from .theme import ResolvedTheme
from .vector import clip_vector, write_empty_boundary_layer


def build_region(
    region: Region,
    output_dir: Path,
    *,
    land: Path | None = None,
    coastline: Path | None = None,
    labels: Path | None = None,
    bathymetry: Path | None = None,
    boundary_file: Path | None = None,
    bathymetry_width: int | None = 6000,
    bathymetry_prepared_for_region: bool = False,
    output_name: str | None = None,
    profile: dict | None = None,
    layout: dict | None = None,
    theme: ResolvedTheme | None = None,
    source_manifest: list[dict] | None = None,
    repository_root: Path | None = None,
    build_timestamp_utc: str | None = None,
    product: dict | None = None,
    visible_footer: bool = True,
    source_coverage_bbox: tuple[float, float, float, float] | None = None,
    vector_coverage_bbox: tuple[float, float, float, float] | None = None,
    vector_longitude_convention: str | None = None,
) -> dict:
    output_name = output_name or region.name
    region_dir = output_dir / output_name
    region_dir.mkdir(parents=True, exist_ok=True)
    gpkg = region_dir / "base.gpkg"
    if gpkg.exists():
        gpkg.unlink()

    coverage_bbox = source_coverage_bbox or region.bbox
    vector_bbox = vector_coverage_bbox or coverage_bbox
    vector_convention = vector_longitude_convention or region.longitude_convention
    counts = {}
    mode = "w"
    if land:
        counts["land"] = clip_vector(land, gpkg, None, vector_bbox, vector_convention, "land", mode)
        mode = "a"
    if coastline:
        counts["coastline"] = clip_vector(
            coastline, gpkg, None, vector_bbox, vector_convention, "coastline", mode
        )
        mode = "a"
    elif land and gpkg.exists():
        land_frame = gpd.read_file(gpkg, layer="land")
        coast_frame = land_frame.copy()
        coast_frame.geometry = coast_frame.geometry.boundary
        coast_frame = coast_frame[~coast_frame.geometry.is_empty]
        coast_frame.to_file(
            gpkg,
            layer="coastline",
            driver="GPKG",
            mode="a",
            index=False,
        )
        counts["coastline"] = len(coast_frame)
        mode = "a"
    if labels:
        counts["labels"] = clip_vector(
            labels, gpkg, None, vector_bbox, vector_convention, "labels", mode
        )
        mode = "a"
    if boundary_file:
        counts["maritime_boundaries"] = clip_vector(
            boundary_file,
            gpkg,
            None,
            vector_bbox,
            vector_convention,
            "maritime_boundaries",
            mode,
        )
    else:
        write_empty_boundary_layer(gpkg, mode="a" if gpkg.exists() else "w")
        counts["maritime_boundaries"] = 0

    bathy_out = None
    if bathymetry:
        bathy_out = region_dir / "bathymetry.tif"
        if bathymetry_prepared_for_region:
            shutil.copy2(bathymetry, bathy_out)
        elif region.longitude_convention == "360":
            clip_raster_360(bathymetry, bathy_out, region.bbox, bathymetry_width)
        else:
            clip_raster(bathymetry, bathy_out, region.bbox, bathymetry_width)

    timestamp = build_timestamp_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    repo = (repository_root or Path.cwd()).resolve()
    style_manifest = theme.manifest() if theme else None
    if style_manifest:
        style_manifest.update(
            {
                "mgrb_version": __version__,
                "cartographic_profile": region.profile,
                "layout_profile": profile.get("layout") if profile else region.layout_scale,
            }
        )
    metadata_dir = region_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    source_payload = {
        "schema": "mgrb-source-manifest-1.0",
        "manifest_id": f"{output_name}-sources",
        "sources": source_manifest or [],
    }
    source_path = metadata_dir / "mgrb-source-manifest.json"
    source_path.write_text(
        json.dumps(source_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_hash = sha256(source_path)
    if style_manifest:
        (metadata_dir / "resolved-theme.json").write_text(
            json.dumps(theme.data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (metadata_dir / "mgrb-style-manifest.json").write_text(
            json.dumps(style_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    product = product or {}
    commit = git_commit(repo)
    citation_template = str(product.get("recommended_citation", ""))
    recommended_citation = citation_template.format(
        mgrb_version=__version__, build_id=output_name, git_commit=commit or "unknown"
    )

    resolved_layout = (
        resolve_layout_geometry(region.bbox, layout)
        if layout and ("orientation_pages_mm" in layout or "map_mm" in layout)
        else dict(layout or {})
    )
    build_manifest = {
        "schema": "mgrb-build-1.0",
        "mgrb_version": __version__,
        "formal_name": product.get("formal_name", "Maritime Geospatial Research Base (MGRB)"),
        "canonical_repository": product.get("canonical_repository"),
        "release_persistent_identifier": product.get("release_persistent_identifier"),
        "canonical_release": {
            "manifest_url": product.get("release_manifest_url"),
            "manifest_sha256": product.get("release_manifest_sha256"),
            "signature_url": product.get("release_signature_url"),
        },
        "git_commit": commit,
        "build_timestamp_utc": timestamp,
        "build_id": output_name,
        "region_profile": region.name,
        "cartographic_profile": region.profile,
        "layout_profile": profile.get("layout") if profile else region.layout_scale,
        "layout_orientation": resolved_layout.get("orientation"),
        "page_mm": resolved_layout.get("page_mm"),
        "map_mm": resolved_layout.get("map_mm"),
        "crs": region.display_crs,
        "longitude_convention": region.longitude_convention,
        "source_coverage_bbox": list(coverage_bbox),
        "vector_coverage_bbox": list(vector_bbox),
        "vector_longitude_convention": vector_convention,
        "visible_footer": visible_footer,
        "recommended_citation": recommended_citation,
        "source_manifest_id": source_payload["manifest_id"],
        "source_manifest_sha256": source_hash,
        "theme": {
            "palette_id": theme.palette_id,
            "palette_origin": theme.origin,
            "palette_sha256": theme.sha256,
            "style_overrides": theme.style_overrides,
        }
        if theme
        else None,
        "sources": source_manifest or [],
    }
    (metadata_dir / "mgrb-build.json").write_text(
        json.dumps(build_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if gpkg.exists():
        with sqlite3.connect(gpkg) as connection:
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
                  md_parent_id INTEGER,
                  FOREIGN KEY (md_file_id) REFERENCES gpkg_metadata(id),
                  FOREIGN KEY (md_parent_id) REFERENCES gpkg_metadata(id)
                );
                """
            )
            connection.execute(
                "INSERT INTO gpkg_metadata(md_scope, md_standard_uri, mime_type, metadata) "
                "VALUES (?, ?, ?, ?)",
                (
                    "dataset",
                    "urn:mgrb:schema:build-lineage:1.0",
                    "application/json",
                    json.dumps(build_manifest, sort_keys=True),
                ),
            )
            connection.commit()

    spec = {
        "build": build_manifest,
        "region": {
            **asdict(region),
            "source_coverage_bbox": list(coverage_bbox),
            "vector_coverage_bbox": list(vector_bbox),
            "vector_longitude_convention": vector_convention,
        },
        "cartographic_profile": profile or {},
        "layout": resolved_layout,
        "theme": style_manifest,
        "sources": source_manifest or [],
        "files": {
            "base_gpkg": gpkg.relative_to(output_dir).as_posix() if gpkg.exists() else None,
            "bathymetry": bathy_out.relative_to(output_dir).as_posix() if bathy_out else None,
            "build_manifest": (metadata_dir / "mgrb-build.json").relative_to(output_dir).as_posix(),
            "source_manifest": source_path.relative_to(output_dir).as_posix(),
            "style_manifest": (metadata_dir / "mgrb-style-manifest.json")
            .relative_to(output_dir)
            .as_posix()
            if style_manifest
            else None,
        },
        "feature_counts": counts,
    }
    (region_dir / "project-spec.json").write_text(
        json.dumps(spec, indent=2) + "\n", encoding="utf-8"
    )
    return spec


def clean_output(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
