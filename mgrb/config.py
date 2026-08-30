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
    profile: str = "regional"
    gebco_stride: int = 12
    context_sources: dict[str, tuple[str, ...]] | None = None
    research_preset: bool = False
    base_region: str | None = None
    title: str = ""
    default_actors: tuple[str, ...] = ()
    base_build_id: str | None = None
    public_evidence_sources: tuple[str, ...] = ()
    orientation_labels: tuple[dict[str, Any], ...] = ()
    media_title: str = ""
    media_subtitle: str = ""


@dataclass(frozen=True)
class CartographicProfile:
    name: str
    purpose: str
    coastline_detail: str
    contour_levels_m: tuple[int, ...]
    contour_width_mm: float
    contour_opacity: float
    bathymetry_opacity: float
    label_rank_max: int
    label_size_pt: float
    graticule_interval_degrees: float
    graticule_enabled: bool
    graticule_width_mm: float
    graticule_opacity: float
    graticule_annotation: bool
    scale_bar: bool
    legend_enabled: bool
    layout: str


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
            profile=str(cfg.get("profile", cfg.get("layout_scale", "regional"))),
            gebco_stride=int(cfg.get("gebco_stride", 12)),
            context_sources={
                layer: tuple(str(source_id) for source_id in source_ids)
                for layer, source_ids in cfg.get("context_sources", {}).items()
            },
            research_preset=bool(cfg.get("research_preset", False)),
            base_region=str(cfg["base_region"]) if cfg.get("base_region") else None,
            title=str(cfg.get("title", cfg.get("purpose", name))),
            default_actors=tuple(str(value).upper() for value in cfg.get("default_actors", ())),
            base_build_id=str(cfg["base_build_id"]) if cfg.get("base_build_id") else None,
            public_evidence_sources=tuple(
                str(value) for value in cfg.get("public_evidence_sources", ())
            ),
            orientation_labels=tuple(dict(value) for value in cfg.get("orientation_labels", ())),
            media_title=str(cfg.get("media_title", "")),
            media_subtitle=str(cfg.get("media_subtitle", "")),
        )
    return out


def load_profiles(path: Path) -> dict[str, CartographicProfile]:
    raw = load_yaml(path).get("profiles", {})
    profiles: dict[str, CartographicProfile] = {}
    for name, cfg in raw.items():
        profiles[name] = CartographicProfile(
            name=name,
            purpose=str(cfg["purpose"]),
            coastline_detail=str(cfg["coastline_detail"]),
            contour_levels_m=tuple(int(value) for value in cfg["contour_levels_m"]),
            contour_width_mm=float(cfg["contour_width_mm"]),
            contour_opacity=float(cfg.get("contour_opacity", 1.0)),
            bathymetry_opacity=float(cfg.get("bathymetry_opacity", 1.0)),
            label_rank_max=int(cfg["label_rank_max"]),
            label_size_pt=float(cfg["label_size_pt"]),
            graticule_interval_degrees=float(cfg["graticule_interval_degrees"]),
            graticule_enabled=bool(cfg.get("graticule_enabled", True)),
            graticule_width_mm=float(cfg.get("graticule_width_mm", 0.10)),
            graticule_opacity=float(cfg.get("graticule_opacity", 1.0)),
            graticule_annotation=bool(cfg["graticule_annotation"]),
            scale_bar=bool(cfg["scale_bar"]),
            legend_enabled=bool(cfg.get("legend_enabled", True)),
            layout=str(cfg["layout"]),
        )
    return profiles
