#!/usr/bin/env python3
"""Split line geometries geodesically at the antimeridian using QGIS Processing."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem  # type: ignore
from processing.core.Processing import Processing  # type: ignore
import processing  # type: ignore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()

    app = QgsApplication([], False)
    app.initQgis()
    Processing.initialize()
    try:
        processing.run(
            "native:antimeridiansplit",
            {
                "INPUT": str(args.input),
                "OUTPUT": str(args.output),
            },
        )
        print(args.output)
    finally:
        app.exitQgis()


if __name__ == "__main__":
    main()
