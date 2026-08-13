from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
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
