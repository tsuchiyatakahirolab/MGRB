from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class BuildRequest:
    region: str
    profile: str
    theme: str
    output_root: Path
    build_id: str | None = None
    visible_footer: bool = True


@dataclass(frozen=True)
class BuildResult:
    build_id: str
    output: Path
    qgis_output: Path


def _has_pyqgis() -> bool:
    try:
        return bool(importlib.util.find_spec("qgis.core"))
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def execute_build(request: BuildRequest, repository_root: Path) -> BuildResult:
    root = repository_root.resolve()
    theme_id = Path(request.theme).stem
    build_id = request.build_id or (
        f"{request.region}-{request.profile}-{theme_id}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    prepare_command = [
        sys.executable,
        str(root / "scripts/prepare_owner_review.py"),
        "--region",
        request.region,
        "--profile",
        request.profile,
        "--theme",
        request.theme,
        "--output-name",
        build_id,
    ]
    if not request.visible_footer:
        prepare_command.append("--no-visible-footer")
    subprocess.run(prepare_command, cwd=root, check=True)

    package_dir = (request.output_root / build_id).resolve()
    qgis_output = package_dir / "qgis"
    config_dir = root / ".tmp/qgis-profile"
    local_app_data = root / ".tmp/qgis-localappdata"
    matplotlib_cache = root / ".tmp/matplotlib"
    config_dir.mkdir(parents=True, exist_ok=True)
    local_app_data.mkdir(parents=True, exist_ok=True)
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QGIS_CUSTOM_CONFIG_PATH": str(config_dir),
            "QGIS_AUTH_DB_DIR_PATH": str(config_dir),
            "XDG_CONFIG_HOME": str(config_dir),
            "LOCALAPPDATA": str(local_app_data),
            "MPLCONFIGDIR": str(matplotlib_cache),
        }
    )
    qgis_args = [
        str(root / "scripts/build_qgis_projects.py"),
        "--build-id",
        build_id,
        "--output",
        str(qgis_output),
        "--review-output",
        str(package_dir),
    ]
    configured_qgis = os.environ.get("MGRB_QGIS_PYTHON")
    local_qgis = root / ".tools/qgis-runtime/QGIS 3.44.12/bin/python-qgis-ltr.bat"
    if _has_pyqgis():
        command = [sys.executable, *qgis_args]
    elif configured_qgis:
        command = [configured_qgis, *qgis_args]
    elif os.name == "nt" and local_qgis.exists():
        command = ["cmd.exe", "/d", "/c", str(local_qgis), *qgis_args]
    else:
        raise RuntimeError(
            "PyQGIS runtime not found. Run inside docker/Dockerfile.qgis or set "
            "MGRB_QGIS_PYTHON to the QGIS Python launcher."
        )
    subprocess.run(command, cwd=root, env=environment, check=True)
    return BuildResult(build_id=build_id, output=package_dir, qgis_output=qgis_output)
