from pathlib import Path

import numpy as np

from mgrb.cartography import buffered_bbox, layout_qa, resolve_layout_geometry
from mgrb.config import load_yaml
from mgrb.render_qa import detect_tofu_blocks

ROOT = Path(__file__).resolve().parents[1]


def test_layout_orientation_adapts_to_research_extent():
    layouts = load_yaml(ROOT / "config/layouts.yml")["layouts"]
    taiwan = resolve_layout_geometry((119.0, 18.5, 124.5, 25.5), layouts["article_local"])
    east_asia = resolve_layout_geometry((115.0, 15.0, 145.0, 45.0), layouts["article_regional"])
    pacific = resolve_layout_geometry((100.0, -60.0, 300.0, 70.0), layouts["article_pacific"])
    assert taiwan["orientation"] == "portrait"
    assert east_asia["orientation"] == "square"
    assert pacific["orientation"] == "landscape"
    for bbox, resolved in (
        ((119.0, 18.5, 124.5, 25.5), taiwan),
        ((115.0, 15.0, 145.0, 45.0), east_asia),
        ((100.0, -60.0, 300.0, 70.0), pacific),
    ):
        qa = layout_qa(resolved, bbox)
        assert qa["orientation_is_adaptive"]
        assert not qa["excessive_blank_margins"]
        assert not qa["awkward_map_frame"]


def test_public_source_bbox_buffers_all_frame_edges_and_clamps_longitude():
    local = buffered_bbox((119.0, 18.5, 124.5, 25.5), "180", "local")
    assert local == (117.5, 16.96, 126.0, 27.04)
    west = buffered_bbox((100.0, -10.0, 179.999, 55.0), "180", "theatre")
    assert west[0] < 100 and west[1] < -10 and west[2] == 180.0 and west[3] > 55
    pacific = buffered_bbox((100.0, -60.0, 300.0, 70.0), "360", "theatre")
    assert pacific == (0.0, -89.0, 360.0, 89.0)


def test_tofu_detector_rejects_repeated_solid_missing_glyph_blocks():
    image = np.full((80, 240, 3), 255, dtype=np.uint8)
    for x in (10, 40, 70, 100):
        image[20:42, x : x + 20] = 0
    rejected = detect_tofu_blocks(image)
    assert rejected["passed"] is False
    clean = np.full((80, 240, 3), 255, dtype=np.uint8)
    clean[20:42, 10:13] = 0
    assert detect_tofu_blocks(clean)["passed"] is True
