from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pyproj import CRS

from .config import load_regions

BACKGROUND_PRESETS: dict[str, dict[str, Any]] = {
    "clean-publication": {
        "label": "Clean publication",
        "theme": "print-muted",
        "bathymetry": True,
        "relief": False,
    },
    "bathymetry": {
        "label": "Bathymetry",
        "theme": "overlay-quiet",
        "bathymetry": True,
        "relief": False,
    },
    "bathymetry-relief": {
        "label": "Bathymetry + relief/hillshade",
        "theme": "canonical",
        "bathymetry": True,
        "relief": True,
    },
    "minimal-grayscale": {
        "label": "Minimal grayscale",
        "theme": "grayscale",
        "bathymetry": True,
        "relief": False,
    },
    "navigation-context": {
        "label": "Navigation/context",
        "theme": "overlay-quiet",
        "bathymetry": True,
        "traffic_density": True,
    },
    "satellite-reference": {
        "label": "Satellite/imagery reference",
        "theme": "overlay-quiet",
        "network_optional": True,
        "availability": "PROVIDER_CONFIGURATION_REQUIRED",
    },
    "none": {
        "label": "No background",
        "theme": "overlay-quiet",
        "bathymetry": False,
        "relief": False,
    },
}

MARITIME_LAYERS: dict[str, dict[str, str]] = {
    "territorial_sea": {
        "label": "Territorial Sea",
        "status": "provider_reference",
    },
    "contiguous_zone": {
        "label": "Contiguous Zone",
        "status": "provider_reference",
    },
    "eez_reference": {
        "label": "EEZ / Reference EEZ",
        "status": "provider_reference",
    },
    "maritime_boundary": {
        "label": "Maritime boundary",
        "status": "source_specific",
    },
    "continental_shelf": {
        "label": "Continental Shelf",
        "status": "source_specific",
    },
    "computed_median": {
        "label": "Computed median/equidistance reference",
        "status": "COMPUTED_REFERENCE",
    },
    "custom_boundary": {
        "label": "Custom boundary layer",
        "status": "user_supplied",
    },
}

DEFAULT_MARITIME_LAYERS = ("eez_reference", "territorial_sea")
OUTPUT_TYPES = ("preview", "paper", "media", "qgis")


@dataclass(frozen=True)
class ProductBuildSpec:
    area: str
    background: str = "bathymetry"
    maritime_layers: tuple[str, ...] = DEFAULT_MARITIME_LAYERS
    input_files: tuple[str, ...] = ()
    outputs: tuple[str, ...] = OUTPUT_TYPES
    custom_extent: tuple[float, float, float, float] | None = None
    field_maps: dict[str, dict[str, str]] | None = None
    include_public_observations: bool = False
    visible_footer: bool = True
    start_date: str | None = None
    end_date: str | None = None
    actors: tuple[str, ...] = ()

    def validate(self, root: Path) -> None:
        regions = load_regions(root / "config" / "regions.yml")
        if self.area != "custom" and self.area not in regions:
            raise ValueError(f"Unknown area: {self.area}")
        if self.area == "custom":
            validate_custom_extent(self.custom_extent)
        elif self.custom_extent is not None:
            raise ValueError("custom_extent is only valid when area is 'custom'")
        if self.background not in BACKGROUND_PRESETS:
            raise ValueError(f"Unknown background: {self.background}")
        unknown_layers = set(self.maritime_layers) - set(MARITIME_LAYERS)
        if unknown_layers:
            raise ValueError(f"Unknown maritime layers: {sorted(unknown_layers)}")
        unknown_outputs = set(self.outputs) - set(OUTPUT_TYPES)
        if unknown_outputs:
            raise ValueError(f"Unknown output types: {sorted(unknown_outputs)}")
        if not self.outputs:
            raise ValueError("Select at least one output")
        start = date.fromisoformat(self.start_date) if self.start_date else None
        end = date.fromisoformat(self.end_date) if self.end_date else None
        if start and end and start > end:
            raise ValueError("start_date must be on or before end_date")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProductBuildSpec:
        custom = payload.get("custom_extent")
        return cls(
            area=str(payload.get("area", "")),
            background=str(payload.get("background", "bathymetry")),
            maritime_layers=tuple(payload.get("maritime_layers", DEFAULT_MARITIME_LAYERS)),
            input_files=tuple(payload.get("input_files", ())),
            outputs=tuple(payload.get("outputs", OUTPUT_TYPES)),
            custom_extent=tuple(float(value) for value in custom) if custom else None,
            field_maps=payload.get("field_maps"),
            include_public_observations=bool(payload.get("include_public_observations", False)),
            visible_footer=bool(payload.get("visible_footer", True)),
            start_date=str(payload["start_date"]) if payload.get("start_date") else None,
            end_date=str(payload["end_date"]) if payload.get("end_date") else None,
            actors=tuple(str(value) for value in payload.get("actors", ())),
        )


def validate_custom_extent(
    extent: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float]:
    if extent is None or len(extent) != 4:
        raise ValueError("Custom extent requires west, south, east, north")
    west, south, east, north = (float(value) for value in extent)
    if not (-180 <= west < east <= 180):
        raise ValueError("Custom longitude extent must satisfy -180 <= west < east <= 180")
    if not (-90 <= south < north <= 90):
        raise ValueError("Custom latitude extent must satisfy -90 <= south < north <= 90")
    if east - west > 300:
        raise ValueError("Custom extent wider than 300 degrees requires a Pacific preset")
    return west, south, east, north


def custom_region_defaults(extent: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = validate_custom_extent(extent)
    lon0 = (west + east) / 2
    lat0 = (south + north) / 2
    width = east - west
    height = north - south
    span = max(width, height)
    profile = "local" if span <= 8 else "regional" if span <= 45 else "theatre"
    if profile == "theatre":
        crs = f"+proj=robin +lon_0={lon0:g} +datum=WGS84 +units=m +no_defs +type=crs"
    else:
        crs = f"+proj=laea +lat_0={lat0:g} +lon_0={lon0:g} +datum=WGS84 +units=m +no_defs +type=crs"
    CRS.from_user_input(crs)
    orientation = (
        "portrait" if height / width >= 1.2 else "landscape" if width / height >= 1.2 else "square"
    )
    return {
        "bbox": [west, south, east, north],
        "display_crs": crs,
        "profile": profile,
        "orientation": orientation,
        "label_density": "high"
        if profile == "local"
        else "medium"
        if profile == "regional"
        else "low",
    }


def product_catalog(root: Path) -> dict[str, Any]:
    regions = load_regions(root / "config" / "regions.yml")
    area_order = (
        "taiwan-east",
        "taiwan-south",
        "taiwan-strait",
        "bashi-luzon-strait",
        "east-china-sea",
        "south-china-sea",
        "west_pacific",
        "pacific_360",
        "xue-long-arctic-2012",
    )
    areas = []
    for name in area_order:
        region = regions[name]
        areas.append(
            {
                "id": name,
                "label": region.title or name.replace("-", " ").title(),
                "purpose": region.purpose,
                "bbox": list(region.bbox),
                "profile": region.profile,
                "projection": region.display_crs,
            }
        )
    areas.append({"id": "custom", "label": "Custom extent", "purpose": "User coordinates"})
    return {
        "schema": "mgrb-product-catalog-1.0",
        "areas": areas,
        "backgrounds": [dict(id=key, **value) for key, value in BACKGROUND_PRESETS.items()],
        "maritime_layers": [dict(id=key, **value) for key, value in MARITIME_LAYERS.items()],
        "outputs": list(OUTPUT_TYPES),
        "defaults": {
            "area": "taiwan-east",
            "background": "bathymetry",
            "maritime_layers": list(DEFAULT_MARITIME_LAYERS),
            "outputs": list(OUTPUT_TYPES),
        },
    }


def safe_build_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.")
    if not normalized:
        raise ValueError("Build ID must contain a letter or number")
    return normalized[:96]


def write_build_spec(spec: ProductBuildSpec, path: Path, root: Path) -> Path:
    spec.validate(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
