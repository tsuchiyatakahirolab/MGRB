from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

FONT_FAMILY = "Noto Sans"
FONT_FILES = ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf")


def register_bundled_fonts(repository_root: Path) -> dict[str, Any]:
    """Register release-pinned OFL fonts in a headless Qt/QGIS process."""
    from qgis.PyQt.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetricsF

    font_dir = repository_root / "assets/fonts"
    registered: list[dict[str, Any]] = []
    for filename in FONT_FILES:
        path = font_dir / filename
        if not path.is_file():
            raise RuntimeError(f"Bundled release font is missing: {path}")
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            raise RuntimeError(f"Qt could not register bundled font: {path}")
        families = list(QFontDatabase.applicationFontFamilies(font_id))
        if FONT_FAMILY not in families:
            raise RuntimeError(f"Unexpected family in bundled font {path}: {families}")
        registered.append({"path": path.relative_to(repository_root).as_posix(), "families": families})

    font = QFont(FONT_FAMILY, 12)
    resolved_family = QFontInfo(font).family()
    if resolved_family != FONT_FAMILY:
        raise RuntimeError(
            f"Bundled font substitution failed: requested {FONT_FAMILY}, got {resolved_family}"
        )
    required = (
        "MGRB v1.0 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        " °−–·,;/()"
    )
    missing = [character for character in required if not QFontMetricsF(font).inFont(character)]
    if missing:
        raise RuntimeError(f"Bundled font lacks required release glyphs: {missing!r}")
    return {
        "family": FONT_FAMILY,
        "resolved_family": resolved_family,
        "files": registered,
        "required_glyphs_present": True,
    }


def glyph_fingerprint(font: Any, text: str) -> str:
    """Return a stable rendered-glyph fingerprint for diagnostic validation."""
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor, QImage, QPainter

    image_format = QImage.Format.Format_ARGB32 if hasattr(QImage.Format, "Format_ARGB32") else QImage.Format_ARGB32
    image = QImage(256, 64, image_format)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    alignment = Qt.AlignmentFlag.AlignLeft if hasattr(Qt, "AlignmentFlag") else Qt.AlignLeft
    painter.drawText(image.rect(), int(alignment), text)
    painter.end()
    payload = image.bits().asstring(image.sizeInBytes())
    return hashlib.sha256(payload).hexdigest()
