#!/usr/bin/env python3
"""Create a tiny synthetic fixture to validate MGRB's QGIS automation in CI.

The geometries are intentionally synthetic and exist only under CI outputs; they are
never distributed as research geography.
"""
from __future__ import annotations
import json
from pathlib import Path
from osgeo import gdal, ogr, osr  # type: ignore

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
    add_layer(ds, "land", ogr.wkbPolygon, "POLYGON((120 20,123 20,123 24,120 24,120 20))", {"name": "fixture"})
    add_layer(ds, "coastline", ogr.wkbLineString, "LINESTRING(120 20,123 24)", {"name": "fixture"})
    add_layer(
        ds,
        "maritime_boundaries",
        ogr.wkbLineString,
        "LINESTRING(121 19,121 25)",
        {"source_id": "fixture", "boundary_type": "eez_reference", "legal_status": "provider_reference"},
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

    spec = {
        "region": {
            "name": "test_region",
            "bbox": [119.0, 18.5, 124.5, 25.5],
            "longitude_convention": "180",
            "display_crs": "+proj=laea +lat_0=22 +lon_0=122 +datum=WGS84 +units=m +no_defs +type=crs",
            "purpose": "CI-only synthetic fixture",
            "layout_scale": "local",
        },
        "files": {
            "base_gpkg": "test_region/base.gpkg",
            "bathymetry": "test_region/bathymetry.tif",
        },
        "feature_counts": {"land": 1, "coastline": 1, "maritime_boundaries": 1},
    }
    (OUT / "project-spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(OUT / "project-spec.json")


if __name__ == "__main__":
    main()
