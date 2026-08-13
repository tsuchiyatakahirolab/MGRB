from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from mgrb.vector import clip_vector


def test_invalid_provider_geometry_is_repaired_before_360_clip(tmp_path: Path):
    source = tmp_path / "invalid.gpkg"
    output = tmp_path / "clipped.gpkg"
    bowtie = Polygon([(-5, 0), (5, 10), (-5, 10), (5, 0), (-5, 0)])
    gpd.GeoDataFrame({"name": ["invalid-provider-feature"]}, geometry=[bowtie], crs=4326).to_file(
        source, layer="land", driver="GPKG"
    )
    count = clip_vector(source, output, "land", (350, -5, 360, 15), "360", "land")
    repaired = gpd.read_file(output, layer="land")
    assert count == 1
    assert repaired.geometry.is_valid.all()


def test_360_clip_splits_source_geometry_before_shifting(tmp_path: Path):
    source = tmp_path / "wide.gpkg"
    output = tmp_path / "clipped.gpkg"
    wide = Polygon([(-170, -10), (170, -10), (170, 10), (-170, 10), (-170, -10)])
    gpd.GeoDataFrame({"name": ["wide"]}, geometry=[wide], crs=4326).to_file(
        source, layer="land", driver="GPKG"
    )
    clip_vector(source, output, "land", (100, -20, 300, 20), "360", "land")
    result = gpd.read_file(output, layer="land")
    assert result.geometry.is_valid.all()
    assert len(result) == 2
    assert all(geometry.bounds[2] - geometry.bounds[0] <= 110 for geometry in result.geometry)
