#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from mgrb.vector import clip_vector

p = argparse.ArgumentParser(
    description="Ingest a user-obtained Marine Regions layer without redistributing the upstream file."
)
p.add_argument("input", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--layer", default="")
p.add_argument("--bbox", nargs=4, required=True, type=float)
p.add_argument("--longitude", choices=["180", "360"], default="180")
a = p.parse_args()
print("Reminder: retain Marine Regions citation and provider terms in downstream metadata.")
clip_vector(a.input, a.output, a.layer, tuple(a.bbox), a.longitude)
print(a.output)
