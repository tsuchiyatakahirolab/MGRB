#!/usr/bin/env python3
"""Fetch small/version-pinned public vector source packages used by MGRB.

Large or provider-gated sources are intentionally not fetched here:
- GEBCO: use the provider's global/tile/subset/OPeNDAP service.
- Marine Regions: obtain directly under provider terms, then ingest locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCES = {
    "natural_earth_5_1_2": {
        "url": "https://github.com/nvkelso/natural-earth-vector/archive/refs/tags/v5.1.2.zip",
        "filename": "natural-earth-vector-v5.1.2.zip",
    },
    "gshhg_2_3_7": {
        "url": "https://ftp.soest.hawaii.edu/gshhg/gshhg-shp-2.3.7.zip",
        "filename": "gshhg-shp-2.3.7.zip",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, path.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", choices=sorted(SOURCES), default=list(SOURCES))
    ap.add_argument("--output", type=Path, default=Path("data/raw/downloads"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    records = []
    for source_id in args.sources:
        item = SOURCES[source_id]
        dst = args.output / item["filename"]
        if not dst.exists() or args.force:
            print(f"fetch {source_id}: {item['url']}")
            download(item["url"], dst)
        records.append(
            {
                "source_id": source_id,
                "original_url": item["url"],
                "local_file": str(dst),
                "bytes": dst.stat().st_size,
                "sha256": sha256(dst),
                "retrieved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            }
        )

    manifest = args.output / "acquisition-manifest.json"
    manifest.write_text(json.dumps({"sources": records}, indent=2) + "\n", encoding="utf-8")
    print(manifest)
    print("GEBCO and Marine Regions are intentionally provider-acquired; see docs/data-sources.md.")


if __name__ == "__main__":
    main()
