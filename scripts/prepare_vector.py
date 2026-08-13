#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from mgrb.vector import clip_vector

p = argparse.ArgumentParser(description="Clip a public vector layer into an MGRB GeoPackage.")
p.add_argument("input", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--layer", default="")
p.add_argument("--bbox", nargs=4, required=True, type=float, metavar=("XMIN","YMIN","XMAX","YMAX"))
p.add_argument("--longitude", choices=["180","360"], default="180")
a = p.parse_args()
n = clip_vector(a.input, a.output, a.layer, tuple(a.bbox), a.longitude)
print(f"wrote {n} features to {a.output}")
