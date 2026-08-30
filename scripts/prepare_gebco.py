#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from mgrb.raster import clip_raster

p = argparse.ArgumentParser(
    description="Clip a provider-obtained GEBCO GeoTIFF subset for an MGRB region."
)
p.add_argument("input", type=Path)
p.add_argument("output", type=Path)
p.add_argument(
    "--bbox", nargs=4, required=True, type=float, metavar=("XMIN", "YMIN", "XMAX", "YMAX")
)
p.add_argument(
    "--width",
    type=int,
    default=None,
    help="Optional output width for reduced-resolution regional maps",
)
a = p.parse_args()
clip_raster(a.input, a.output, tuple(a.bbox), a.width)
print(a.output)
