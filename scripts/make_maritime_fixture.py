#!/usr/bin/env python3
"""Prepare a clearly synthetic/offline maritime package for the QGIS CI matrix."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mgrb.research_package import ResearchBuildRequest, prepare_research_package

BASE_FIXTURE = ROOT / "outputs/qgis-fixture/derived/test_region"
BASE_TARGET = ROOT / "data" / "derived" / "taiwan-local-canonical"
PACKAGE_ROOT = ROOT / "outputs" / "maritime-fixture"
BUILD_ID = "ci-synthetic-maritime-workspace"


def main() -> None:
    if not (BASE_FIXTURE / "project-spec.json").exists():
        from scripts.make_qgis_fixture import main as make_base_fixture

        make_base_fixture()
    BASE_TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_FIXTURE / "base.gpkg", BASE_TARGET / "base.gpkg")
    shutil.copy2(BASE_FIXTURE / "bathymetry.tif", BASE_TARGET / "bathymetry.tif")
    base_spec = json.loads((BASE_FIXTURE / "project-spec.json").read_text(encoding="utf-8"))
    (BASE_TARGET / "project-spec.json").write_text(
        json.dumps(base_spec, indent=2) + "\n", encoding="utf-8"
    )
    prepared = prepare_research_package(
        ResearchBuildRequest(
            area="taiwan-east",
            output_root=PACKAGE_ROOT,
            build_id=BUILD_ID,
            live_sources=False,
        ),
        ROOT,
    )
    print(prepared.spec_path)


if __name__ == "__main__":
    main()
