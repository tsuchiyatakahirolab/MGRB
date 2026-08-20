from __future__ import annotations

import math
from typing import Any


def geographic_aspect(bbox: tuple[float, float, float, float]) -> float:
    """Approximate mapped width/height while accounting for latitude."""
    xmin, ymin, xmax, ymax = bbox
    height = max(ymax - ymin, 1e-9)
    mid_latitude = (ymin + ymax) / 2.0
    return (xmax - xmin) * max(math.cos(math.radians(mid_latitude)), 0.15) / height


def select_orientation(bbox: tuple[float, float, float, float]) -> str:
    aspect = geographic_aspect(bbox)
    if aspect < 0.85:
        return "portrait"
    if aspect > 1.30:
        return "landscape"
    return "square"


def resolve_layout_geometry(
    bbox: tuple[float, float, float, float], layout: dict[str, Any]
) -> dict[str, Any]:
    """Resolve adaptive page and map geometry while retaining legacy fixed layouts."""
    resolved = dict(layout)
    orientation_pages = layout.get("orientation_pages_mm")
    if not orientation_pages:
        page_width, page_height = [float(value) for value in layout["page_mm"]]
        orientation = "landscape" if page_width > page_height else "portrait"
        if math.isclose(page_width, page_height):
            orientation = "square"
        resolved["orientation"] = orientation
        resolved["map_area_ratio"] = (
            float(layout["map_mm"][2])
            * float(layout["map_mm"][3])
            / (page_width * page_height)
        )
        return resolved

    orientation = select_orientation(bbox)
    page_width, page_height = [float(value) for value in orientation_pages[orientation]]
    side_margin = float(layout.get("side_margin_mm", 8.0))
    map_top = float(layout.get("map_top_mm", 12.0))
    map_bottom = float(layout.get("map_bottom_mm", 12.0))
    map_width = page_width - 2.0 * side_margin
    map_height = page_height - map_top - map_bottom
    resolved.update(
        {
            "orientation": orientation,
            "page_mm": [page_width, page_height],
            "map_mm": [side_margin, map_top, map_width, map_height],
            "map_area_ratio": map_width * map_height / (page_width * page_height),
        }
    )
    return resolved


def buffered_bbox(
    bbox: tuple[float, float, float, float],
    longitude_convention: str,
    profile: str,
) -> tuple[float, float, float, float]:
    """Return deterministic public-source coverage beyond the final map frame."""
    if longitude_convention == "360" and bbox[2] - bbox[0] >= 180.0:
        # A rectangular Robinson frame includes inverse-projectable longitudes well
        # beyond the research bbox near its curved edges; global raster coverage
        # prevents those valid areas from exposing a subset footprint.
        return (0.0, -89.0, 360.0, 89.0)
    return buffered_vector_bbox(bbox, longitude_convention, profile)


def buffered_vector_bbox(
    bbox: tuple[float, float, float, float],
    longitude_convention: str,
    profile: str,
) -> tuple[float, float, float, float]:
    """Buffer vector context and avoid clipped edges in projected map frames."""
    if longitude_convention == "360" and bbox[2] - bbox[0] >= 180.0:
        return (0.0, -89.0, 360.0, 89.0)
    fractions = {"local": 0.22, "regional": 0.30, "theatre": 0.15}
    minimums = {"local": 1.5, "regional": 3.0, "theatre": 8.0}
    fraction = fractions.get(profile, 0.18)
    minimum = minimums.get(profile, 3.0)
    xmin, ymin, xmax, ymax = bbox
    x_buffer = max((xmax - xmin) * fraction, minimum)
    y_buffer = max((ymax - ymin) * fraction, minimum)
    longitude_minimum, longitude_maximum = (
        (0.0, 360.0) if longitude_convention == "360" else (-180.0, 180.0)
    )
    return (
        max(longitude_minimum, xmin - x_buffer),
        max(-89.0, ymin - y_buffer),
        min(longitude_maximum, xmax + x_buffer),
        min(89.0, ymax + y_buffer),
    )


def layout_qa(layout: dict[str, Any], bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    page_width, page_height = [float(value) for value in layout["page_mm"]]
    _, _, map_width, map_height = [float(value) for value in layout["map_mm"]]
    orientation = str(layout["orientation"])
    expected = select_orientation(bbox)
    area_ratio = map_width * map_height / (page_width * page_height)
    map_aspect = map_width / map_height
    return {
        "orientation": orientation,
        "expected_orientation": expected,
        "orientation_is_adaptive": orientation == expected,
        "map_area_ratio": area_ratio,
        "excessive_blank_margins": area_ratio < 0.72,
        "map_aspect_ratio": map_aspect,
        "awkward_map_frame": not 0.55 <= map_aspect <= 1.85,
    }
