from __future__ import annotations
from pathlib import Path
import tempfile
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.windows import from_bounds
from .longitude import bbox_360_to_180_parts


def _read_window(ds, bbox, out_width: int | None = None):
    xmin, ymin, xmax, ymax = bbox
    window = from_bounds(xmin, ymin, xmax, ymax, ds.transform).round_offsets().round_lengths()
    if window.width <= 0 or window.height <= 0:
        raise ValueError(f"Empty raster window for bbox {bbox}")
    if out_width and out_width < window.width:
        scale = window.width / out_width
        out_height = max(1, round(window.height / scale))
        data = ds.read(
            out_shape=(ds.count, out_height, out_width),
            window=window,
            resampling=Resampling.bilinear,
        )
        transform = ds.window_transform(window) * Affine.scale(
            window.width / out_width, window.height / out_height
        )
    else:
        data = ds.read(window=window)
        transform = ds.window_transform(window)
    return data, transform


def _output_profile(profile: dict, data, transform) -> dict:
    out = profile.copy()
    out.pop("blockxsize", None)
    out.pop("blockysize", None)
    height = int(data.shape[1])
    width = int(data.shape[2])
    tiled = width >= 32 and height >= 32
    out.update(
        height=height,
        width=width,
        transform=transform,
        compress="deflate",
        tiled=tiled,
    )
    if tiled:
        out["blockxsize"] = min(256, max(16, (width // 16) * 16))
        out["blockysize"] = min(256, max(16, (height // 16) * 16))
    return out


def clip_raster(
    src: Path,
    dst: Path,
    bbox: tuple[float, float, float, float],
    out_width: int | None = None,
) -> None:
    with rasterio.open(src) as ds:
        if ds.crs is None:
            raise ValueError("Input raster has no CRS")
        data, transform = _read_window(ds, bbox, out_width)
        profile = _output_profile(ds.profile, data, transform)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst, "w", **profile) as out:
            out.write(data)


def clip_raster_360(
    src: Path,
    dst: Path,
    bbox_360: tuple[float, float, float, float],
    out_width: int | None = None,
) -> None:
    """Create a 0..360 derivative from a canonical -180..180 geographic raster."""
    parts = bbox_360_to_180_parts(bbox_360)
    if len(parts) == 1:
        with rasterio.open(src) as ds:
            data, transform = _read_window(ds, parts[0], out_width)
            if bbox_360[0] >= 180:
                transform = Affine(
                    transform.a, transform.b, transform.c + 360.0,
                    transform.d, transform.e, transform.f,
                )
            profile = _output_profile(ds.profile, data, transform)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(dst, "w", **profile) as out:
                out.write(data)
        return

    # For a Pacific-spanning bbox, write two temporary rasters and shift the
    # western-hemisphere part +360 degrees before mosaicking.
    with rasterio.open(src) as ds, tempfile.TemporaryDirectory() as td:
        tmp_paths: list[Path] = []
        widths = None
        if out_width:
            span = bbox_360[2] - bbox_360[0]
            widths = [max(1, round(out_width * ((p[2] - p[0]) / span))) for p in parts]
        for i, part in enumerate(parts):
            data, transform = _read_window(ds, part, widths[i] if widths else None)
            if part[0] < 0:
                transform = Affine(
                    transform.a, transform.b, transform.c + 360.0,
                    transform.d, transform.e, transform.f,
                )
            profile = _output_profile(ds.profile, data, transform)
            p = Path(td) / f"part-{i}.tif"
            with rasterio.open(p, "w", **profile) as out:
                out.write(data)
            tmp_paths.append(p)

        opened = [rasterio.open(p) for p in tmp_paths]
        try:
            mosaic, transform = merge(opened)
            profile = _output_profile(opened[0].profile, mosaic, transform)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(dst, "w", **profile) as out:
                out.write(mosaic)
        finally:
            for ds2 in opened:
                ds2.close()
