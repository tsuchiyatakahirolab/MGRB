#!/usr/bin/env python3
"""Create a tiny synthetic fixture to validate MGRB's QGIS automation in CI.

The geometries are intentionally synthetic and exist only under CI outputs; they are
never distributed as research geography.
"""

from __future__ import annotations

import json
from pathlib import Path

from osgeo import gdal, ogr, osr  # type: ignore

from mgrb.config import load_profiles, load_yaml
from mgrb.provenance import sha256
from mgrb.theme import resolve_theme

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/qgis-fixture/derived/test_region"


def add_layer(ds, name: str, geom_type: int, wkt: str, fields: dict[str, str]):
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    layer = ds.CreateLayer(name, srs, geom_type=geom_type)
    for key in fields:
        layer.CreateField(ogr.FieldDefn(key, ogr.OFTString))
    feat = ogr.Feature(layer.GetLayerDefn())
    geom = ogr.CreateGeometryFromWkt(wkt)
    feat.SetGeometry(geom)
    for key, value in fields.items():
        feat.SetField(key, value)
    layer.CreateFeature(feat)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gpkg = OUT / "base.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    driver = ogr.GetDriverByName("GPKG")
    ds = driver.CreateDataSource(str(gpkg))
    add_layer(
        ds,
        "land",
        ogr.wkbPolygon,
        "POLYGON((120 20,123 20,123 24,120 24,120 20))",
        {"name": "fixture"},
    )
    add_layer(ds, "coastline", ogr.wkbLineString, "LINESTRING(120 20,123 24)", {"name": "fixture"})
    add_layer(
        ds,
        "maritime_boundaries",
        ogr.wkbLineString,
        "LINESTRING(121 19,121 25)",
        {
            "source_id": "fixture",
            "boundary_type": "eez_reference",
            "legal_status": "provider_reference",
        },
    )
    ds = None

    tif = OUT / "bathymetry.tif"
    rdriver = gdal.GetDriverByName("GTiff")
    raster = rdriver.Create(str(tif), 55, 70, 1, gdal.GDT_Int16)
    raster.SetGeoTransform((119.0, 0.1, 0, 25.5, 0, -0.1))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    raster.SetProjection(srs.ExportToWkt())
    band = raster.GetRasterBand(1)
    band.Fill(-1000)
    band.SetNoDataValue(-32768)
    band.FlushCache()
    raster = None

    profile = load_profiles(ROOT / "config/profiles.yml")["local"]
    layout = load_yaml(ROOT / "config/layouts.yml")["layouts"][profile.layout]
    theme = resolve_theme("canonical", ROOT / "config/themes")
    style_manifest = theme.manifest()
    style_manifest.update(
        {
            "mgrb_version": "1.0.0",
            "cartographic_profile": "local",
            "layout_profile": profile.layout,
        }
    )
    source_manifest = {
        "schema": "mgrb-source-manifest-1.0",
        "manifest_id": "test_region-sources",
        "sources": [
            {
                "source_id": "ci_synthetic_fixture",
                "provider": "MGRB synthetic CI fixture",
                "dataset": "Clearly synthetic test geometry",
                "version_or_date": "1",
                "url": None,
                "doi": None,
                "licence": "MGRB test fixture",
                "redistribution": None,
                "layers": ["bathymetry", "land", "coastline", "maritime_boundaries"],
                "transformations": ["CI-only synthetic geometry"],
            }
        ],
    }
    metadata_dir = OUT / "metadata"
    metadata_dir.mkdir(exist_ok=True)
    source_path = metadata_dir / "mgrb-source-manifest.json"
    source_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    style_path = metadata_dir / "mgrb-style-manifest.json"
    style_path.write_text(
        json.dumps(style_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    build = {
        "schema": "mgrb-build-1.0",
        "mgrb_version": "1.0.0",
        "formal_name": "Maritime Geospatial Research Base (MGRB)",
        "canonical_repository": None,
        "release_persistent_identifier": None,
        "canonical_release": {
            "manifest_url": None,
            "manifest_sha256": None,
            "signature_url": None,
        },
        "git_commit": "0000000000000000000000000000000000000000",
        "build_timestamp_utc": "2000-01-01T00:00:00+00:00",
        "build_id": "test_region",
        "region_profile": "test_region",
        "cartographic_profile": "local",
        "layout_profile": profile.layout,
        "crs": "+proj=laea +lat_0=22 +lon_0=122 +datum=WGS84 +units=m +no_defs +type=crs",
        "longitude_convention": "180",
        "visible_footer": True,
        "recommended_citation": (
            "Maritime Geospatial Research Base (MGRB), version 1.0.0, "
            "build test_region, Git commit 0000000000000000000000000000000000000000."
        ),
        "source_manifest_id": source_manifest["manifest_id"],
        "source_manifest_sha256": sha256(source_path),
        "theme": {
            "palette_id": theme.palette_id,
            "palette_origin": theme.origin,
            "palette_sha256": theme.sha256,
            "style_overrides": theme.style_overrides,
        },
        "sources": source_manifest["sources"],
    }
    build_path = metadata_dir / "mgrb-build.json"
    build_path.write_text(json.dumps(build, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    spec = {
        "build": build,
        "region": {
            "name": "test_region",
            "bbox": [119.0, 18.5, 124.5, 25.5],
            "longitude_convention": "180",
            "display_crs": "+proj=laea +lat_0=22 +lon_0=122 +datum=WGS84 +units=m +no_defs +type=crs",
            "purpose": "CI-only synthetic fixture",
            "layout_scale": "local",
            "profile": "local",
            "gebco_stride": 4,
            "context_sources": {},
        },
        "cartographic_profile": vars(profile),
        "layout": layout,
        "theme": style_manifest,
        "sources": source_manifest["sources"],
        "files": {
            "base_gpkg": "test_region/base.gpkg",
            "bathymetry": "test_region/bathymetry.tif",
            "build_manifest": "test_region/metadata/mgrb-build.json",
            "source_manifest": "test_region/metadata/mgrb-source-manifest.json",
            "style_manifest": "test_region/metadata/mgrb-style-manifest.json",
        },
        "feature_counts": {"land": 1, "coastline": 1, "maritime_boundaries": 1},
    }
    (OUT / "project-spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(OUT / "project-spec.json")


if __name__ == "__main__":
    main()
