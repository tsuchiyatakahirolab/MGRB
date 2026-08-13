from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from mgrb.builder import build_region
from mgrb.config import Region
from mgrb.raster import clip_raster, clip_raster_360


def _make_world(path: Path):
    # 1-degree synthetic raster used only to test coordinate handling.
    data = np.arange(180 * 360, dtype="int32").reshape(180, 360)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=180,
        width=360,
        count=1,
        dtype="int32",
        crs="EPSG:4326",
        transform=from_origin(-180, 90, 1, 1),
    ) as dst:
        dst.write(data, 1)


def test_clip_raster(tmp_path: Path):
    src = tmp_path / "world.tif"
    out = tmp_path / "clip.tif"
    _make_world(src)
    clip_raster(src, out, (119, 18, 125, 26))
    with rasterio.open(out) as ds:
        assert ds.width == 6
        assert ds.height == 8
        assert round(ds.bounds.left, 6) == 119
        assert round(ds.bounds.right, 6) == 125


def test_clip_raster_360_crosses_dateline(tmp_path: Path):
    src = tmp_path / "world.tif"
    out = tmp_path / "pacific.tif"
    _make_world(src)
    clip_raster_360(src, out, (100, -20, 300, 20))
    with rasterio.open(out) as ds:
        assert round(ds.bounds.left, 6) == 100
        assert round(ds.bounds.right, 6) == 300
        assert round(ds.bounds.bottom, 6) == -20
        assert round(ds.bounds.top, 6) == 20
        assert ds.width == 200
        assert ds.height == 40


def test_prepared_360_raster_is_not_wrapped_twice(tmp_path: Path):
    source = tmp_path / "prepared.tif"
    data = np.zeros((20, 200), dtype="int16")
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        height=20,
        width=200,
        count=1,
        dtype="int16",
        crs="EPSG:4326",
        transform=from_origin(100, 20, 1, 1),
    ) as dataset:
        dataset.write(data, 1)
    region = Region(
        name="prepared_360",
        bbox=(100, 0, 300, 20),
        longitude_convention="360",
        display_crs="EPSG:4326",
    )
    build_region(
        region,
        tmp_path / "derived",
        bathymetry=source,
        bathymetry_prepared_for_region=True,
    )
    with rasterio.open(tmp_path / "derived/prepared_360/bathymetry.tif") as dataset:
        assert dataset.width == 200
        assert dataset.bounds.left == 100
        assert dataset.bounds.right == 300
