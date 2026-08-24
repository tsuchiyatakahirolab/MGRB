from __future__ import annotations

import argparse
import json
from pathlib import Path


def check(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    visual = payload["visual_qa"]
    required_passes = {
        "paper tofu": visual["paper_text"]["passed"],
        "media tofu": visual["media_text"]["passed"],
        "paper raster coverage": visual["raster_coverage"]["passed"],
        "media raster coverage": visual["media_raster_coverage"]["passed"],
        "adaptive layout": visual["layout_geometry"]["orientation_is_adaptive"],
        "scale bar kilometres": visual["scale_bar"]["passed"],
        "context legend": visual["context_legend"]["passed"],
        "paper/media distinction": visual["paper_media_distinction"]["passed"],
        "entity integrity": visual["inferred_entity_integrity"],
        "relative paths": payload["relative_paths"],
        "portable reopen": payload["portable_copy_reopen"],
    }
    failures = [name for name, passed in required_passes.items() if not passed]
    if failures:
        raise SystemExit(f"Maritime QGIS validation failed: {', '.join(failures)}")
    if any(not value for value in payload["artifact_verification"].values()):
        raise SystemExit("Maritime artifact verification contains a failure")
    return {"ok": True, "qgis_version": payload["qgis_version"], "checks": required_passes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("validation", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.validation), indent=2))


if __name__ == "__main__":
    main()
