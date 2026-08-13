from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_yaml

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
REQUIRED_COLOR_PATHS = (
    "bathymetry.trench",
    "bathymetry.abyssal",
    "bathymetry.deep",
    "bathymetry.slope",
    "bathymetry.upper_slope",
    "bathymetry.shelf",
    "land.fill",
    "land.outline",
    "coastline",
    "contours.minor",
    "contours.major",
    "maritime_status.treaty_delimited",
    "maritime_status.officially_declared",
    "maritime_status.provider_reference",
    "maritime_status.computed_reference",
    "maritime_status.disputed",
    "maritime_status.uncertain",
    "uncertainty.fill",
    "labels.text",
    "labels.halo",
    "graticule",
    "layout.background",
    "layout.frame",
    "layout.title",
    "layout.footer",
)


@dataclass(frozen=True)
class ResolvedTheme:
    data: dict[str, Any]
    origin: str
    sha256: str
    style_overrides: bool

    @property
    def palette_id(self) -> str:
        return str(self.data["palette_id"])

    def manifest(self) -> dict[str, Any]:
        return {
            "style_system": "MGRB",
            "style_schema_version": self.data["schema_version"],
            "palette_id": self.palette_id,
            "palette_origin": self.origin,
            "palette_sha256": self.sha256,
            "style_overrides": self.style_overrides,
            "resolved_theme": self.data,
        }


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key not in result:
            raise ValueError(f"Unknown theme key: {key}")
        if isinstance(value, dict):
            if not isinstance(result[key], dict):
                raise TypeError(f"Theme key {key!r} cannot contain nested values")
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"Theme is missing required value: presentation.{dotted}")
        value = value[part]
    return value


def validate_theme(data: dict[str, Any]) -> None:
    if str(data.get("schema_version")) != "1.0":
        raise ValueError("Theme schema_version must be '1.0'")
    if not isinstance(data.get("palette_id"), str) or not data["palette_id"].strip():
        raise ValueError("Theme palette_id must be a non-empty string")
    presentation = data.get("presentation")
    if not isinstance(presentation, dict):
        raise TypeError("Theme presentation must be a mapping")
    for dotted in REQUIRED_COLOR_PATHS:
        color = _get_path(presentation, dotted)
        if not isinstance(color, str) or not HEX_COLOR.fullmatch(color):
            raise ValueError(f"Invalid color at presentation.{dotted}: {color!r}")
    for dotted in ("hillshade.opacity", "uncertainty.opacity"):
        opacity = float(_get_path(presentation, dotted))
        if not 0.0 <= opacity <= 1.0:
            raise ValueError(f"Opacity must be between 0 and 1 at presentation.{dotted}")


def theme_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_theme(theme: str | Path, theme_dir: Path) -> ResolvedTheme:
    canonical = load_yaml(theme_dir / "canonical.yml")
    candidate = Path(theme)
    builtin = theme_dir / f"{theme}.yml"
    if builtin.exists() and not candidate.exists():
        override = load_yaml(builtin)
        origin = "canonical"
        style_overrides = str(theme) != "canonical"
    elif candidate.exists():
        override = load_yaml(candidate)
        origin = "custom"
        style_overrides = True
    else:
        raise ValueError(f"Unknown theme {theme!r}; use a canonical ID or YAML path")
    resolved = _merge(canonical, override)
    validate_theme(resolved)
    return ResolvedTheme(
        data=resolved,
        origin=origin,
        sha256=theme_hash(resolved),
        style_overrides=style_overrides,
    )
