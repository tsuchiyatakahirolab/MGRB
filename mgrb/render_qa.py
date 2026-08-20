from __future__ import annotations

from collections import Counter, deque

import numpy as np


def detect_tofu_blocks(rgb: np.ndarray) -> dict[str, object]:
    """Detect repeated, near-solid square missing-glyph boxes in a text crop."""
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError("Expected an RGB/RGBA image array")
    dark = np.all(rgb[:, :, :3] < 72, axis=2)
    height, width = dark.shape
    seen = np.zeros_like(dark, dtype=bool)
    boxes: list[tuple[int, int]] = []
    for y, x in zip(*np.nonzero(dark & ~seen), strict=False):
        if seen[y, x]:
            continue
        queue = deque([(int(y), int(x))])
        seen[y, x] = True
        pixels: list[tuple[int, int]] = []
        while queue:
            cy, cx = queue.popleft()
            pixels.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < height and 0 <= nx < width and dark[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        if len(pixels) < 20:
            continue
        ys = [point[0] for point in pixels]
        xs = [point[1] for point in pixels]
        box_height = max(ys) - min(ys) + 1
        box_width = max(xs) - min(xs) + 1
        fill = len(pixels) / float(box_height * box_width)
        if (
            6 <= box_width <= 100
            and 6 <= box_height <= 100
            and 0.65 <= box_width / box_height <= 1.35
            and fill >= 0.82
        ):
            boxes.append((box_width, box_height))
    dimensions = Counter((round(w / 2) * 2, round(h / 2) * 2) for w, h in boxes)
    repeated = max(dimensions.values(), default=0)
    return {
        "passed": repeated < 3,
        "candidate_blocks": len(boxes),
        "largest_repeated_dimension_count": repeated,
    }
