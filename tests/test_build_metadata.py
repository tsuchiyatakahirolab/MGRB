import json
from pathlib import Path

from mgrb import __version__
from mgrb.builder import build_region
from mgrb.config import Region
from mgrb.theme import resolve_theme

ROOT = Path(__file__).resolve().parents[1]


def test_build_emits_complete_private_path_free_style_metadata(tmp_path: Path):
    region = Region(
        name="metadata_test",
        bbox=(120.0, 20.0, 121.0, 21.0),
        longitude_convention="180",
        display_crs="EPSG:4326",
        profile="local",
    )
    theme = resolve_theme("canonical", ROOT / "config/themes")
    profile = {"layout": "article_local", "contour_levels_m": [-200, -1000]}
    spec = build_region(
        region,
        tmp_path,
        output_name="metadata-test",
        profile=profile,
        layout={"page_mm": [210, 148]},
        theme=theme,
        source_manifest=[
            {
                "source_id": "public_test",
                "provider": "Public Test Provider",
                "version_or_date": "1",
            }
        ],
        repository_root=ROOT,
        build_timestamp_utc="2026-08-13T00:00:00+00:00",
    )
    manifest_path = tmp_path / "metadata-test/metadata/mgrb-build.json"
    style_path = tmp_path / "metadata-test/metadata/mgrb-style-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    style = json.loads(style_path.read_text(encoding="utf-8"))
    assert manifest["mgrb_version"] == __version__
    assert manifest["region_profile"] == "metadata_test"
    assert manifest["cartographic_profile"] == "local"
    assert manifest["layout_profile"] == "article_local"
    assert manifest["crs"] == "EPSG:4326"
    assert manifest["theme"]["palette_sha256"] == theme.sha256
    assert style["style_system"] == "MGRB"
    assert spec["files"]["build_manifest"] == "metadata-test/metadata/mgrb-build.json"
    public_payload = manifest_path.read_text(encoding="utf-8") + style_path.read_text(
        encoding="utf-8"
    )
    assert str(ROOT) not in public_payload
    assert "C:\\Users" not in public_payload
