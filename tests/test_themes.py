import copy
from pathlib import Path

import pytest
import yaml

from mgrb.theme import resolve_theme, theme_hash, validate_theme

ROOT = Path(__file__).resolve().parents[1]


def test_all_canonical_themes_resolve_and_hash_deterministically():
    for name in ("canonical", "grayscale", "print-muted"):
        first = resolve_theme(name, ROOT / "config/themes")
        second = resolve_theme(name, ROOT / "config/themes")
        assert first.origin == "canonical"
        assert first.sha256 == second.sha256 == theme_hash(first.data)
        assert len(first.sha256) == 64


def test_custom_partial_theme_inherits_without_mutating_canonical(tmp_path: Path):
    canonical_path = ROOT / "config/themes/canonical.yml"
    before = canonical_path.read_bytes()
    custom = tmp_path / "custom.yml"
    custom.write_text(
        "schema_version: '1.0'\npalette_id: custom-test\npresentation:\n  coastline: '#123456'\n",
        encoding="utf-8",
    )
    resolved = resolve_theme(custom, ROOT / "config/themes")
    assert resolved.origin == "custom"
    assert resolved.style_overrides is True
    assert resolved.data["presentation"]["coastline"] == "#123456"
    assert resolved.data["presentation"]["bathymetry"]["shelf"] == "#c8d5d8"
    assert canonical_path.read_bytes() == before


def test_invalid_theme_value_fails_clearly():
    data = yaml.safe_load((ROOT / "config/themes/canonical.yml").read_text(encoding="utf-8"))
    invalid = copy.deepcopy(data)
    invalid["presentation"]["coastline"] = "blue-ish"
    with pytest.raises(ValueError, match="Invalid color"):
        validate_theme(invalid)


def test_theme_does_not_contain_semantic_depth_or_status_definitions():
    for path in (ROOT / "config/themes").glob("*.yml"):
        theme = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "depth_classes" not in theme
        assert "contour_levels_m" not in theme
        assert "status_categories" not in theme
