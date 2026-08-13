from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class Region:
    name: str
    bbox: tuple[float, float, float, float]
    longitude_convention: str
    display_crs: str
    purpose: str = ""
    layout_scale: str = "regional"


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_regions(path: Path) -> dict[str, Region]:
    raw = load_yaml(path).get("regions", {})
    out: dict[str, Region] = {}
    for name, cfg in raw.items():
        if "bbox_360" in cfg:
            bbox = tuple(float(x) for x in cfg["bbox_360"])
            convention = "360"
        else:
            bbox = tuple(float(x) for x in cfg["bbox_180"])
            convention = "180"
        if len(bbox) != 4:
            raise ValueError(f"Region {name!r} bbox must have four values")
        out[name] = Region(
            name=name,
            bbox=bbox,  # type: ignore[arg-type]
            longitude_convention=convention,
            display_crs=str(cfg.get("display_crs", "EPSG:4326")),
            purpose=str(cfg.get("purpose", "")),
            layout_scale=str(cfg.get("layout_scale", "regional")),
        )
    return out
