from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString, Polygon
from mgrb.builder import build_region
from mgrb.config import Region


def test_build_public_region(tmp_path: Path):
    land = tmp_path / "land.gpkg"
    coast = tmp_path / "coast.gpkg"
    bounds = tmp_path / "bounds.gpkg"

    gpd.GeoDataFrame(
        {"name": ["test-land"]},
        geometry=[Polygon([(120, 20), (123, 20), (123, 24), (120, 24)])],
        crs="EPSG:4326",
    ).to_file(land, layer="land", driver="GPKG")
    gpd.GeoDataFrame(
        {"name": ["test-coast"]},
        geometry=[LineString([(120, 20), (123, 24)])],
        crs="EPSG:4326",
    ).to_file(coast, layer="coast", driver="GPKG")
    gpd.GeoDataFrame(
        {"source_id": ["test"], "boundary_type": ["eez_reference"], "legal_status": ["provider_reference"]},
        geometry=[LineString([(121, 19), (121, 25)])],
        crs="EPSG:4326",
    ).to_file(bounds, layer="boundary", driver="GPKG")

    region = Region(
        name="test",
        bbox=(119.0, 18.5, 124.5, 25.5),
        longitude_convention="180",
        display_crs="EPSG:4326",
        purpose="test",
        layout_scale="local",
    )
    spec = build_region(
        region,
        tmp_path / "derived",
        land=land,
        coastline=coast,
        boundary_file=bounds,
    )
    assert spec["feature_counts"] == {"land": 1, "coastline": 1, "maritime_boundaries": 1}
    gpkg = tmp_path / "derived/test/base.gpkg"
    assert len(gpd.read_file(gpkg, layer="land")) == 1
    assert len(gpd.read_file(gpkg, layer="coastline")) == 1
    assert len(gpd.read_file(gpkg, layer="maritime_boundaries")) == 1
