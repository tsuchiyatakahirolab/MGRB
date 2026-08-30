#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer  # type: ignore

from mgrb.qgis_font import register_bundled_fonts

qgs = QgsApplication([], False)
qgs.initQgis()
try:
    font_validation = register_bundled_fonts(Path(__file__).resolve().parents[1])
    project = QgsProject.instance()
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "smoke", "memory")
    assert layer.isValid()
    project.addMapLayer(layer)
    out = Path("outputs/qgis-smoke.qgz")
    out.parent.mkdir(exist_ok=True)
    assert project.write(str(out))
    assert out.exists() and out.stat().st_size > 0
    print(f"QGIS smoke PASS: {out}; font={font_validation['resolved_family']}")
finally:
    qgs.exitQgis()
