from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
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


@dataclass(frozen=True)
class MaritimeBuildRequest:
    area: str
    output_root: Path
    build_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    actors: tuple[str, ...] = ()
    public_data: bool = True
    local_inputs: tuple[Path, ...] = ()
    live_sources: bool = True
    traffic_density: Path | None = None


@dataclass(frozen=True)
class MaritimeBuildResult:
    build_id: str
    output: Path
    qgis_project: Path
    elapsed_seconds: float


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


def _qgis_command(root: Path, script_args: list[str]) -> list[str]:
    configured_qgis = os.environ.get("MGRB_QGIS_PYTHON")
    local_qgis = root / ".tools/qgis-runtime/QGIS 3.44.12/bin/python-qgis-ltr.bat"
    if _has_pyqgis():
        return [sys.executable, *script_args]
    if configured_qgis:
        return [configured_qgis, *script_args]
    if os.name == "nt" and local_qgis.exists():
        return ["cmd.exe", "/d", "/c", str(local_qgis), *script_args]
    raise RuntimeError(
        "PyQGIS runtime not found. Run inside docker/Dockerfile.qgis or set "
        "MGRB_QGIS_PYTHON to the QGIS Python launcher."
    )


def execute_maritime_build(
    request: MaritimeBuildRequest,
    repository_root: Path,
) -> MaritimeBuildResult:
    from .research_package import ResearchBuildRequest, prepare_research_package

    root = repository_root.resolve()
    build_id = request.build_id or (
        f"{request.area}-maritime-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    started = time.perf_counter()
    prepared = prepare_research_package(
        ResearchBuildRequest(
            area=request.area,
            output_root=request.output_root,
            build_id=build_id,
            start_date=request.start_date,
            end_date=request.end_date,
            actors=request.actors,
            public_data=request.public_data,
            local_inputs=request.local_inputs,
            live_sources=request.live_sources,
            traffic_density=request.traffic_density,
        ),
        root,
    )
    environment = os.environ.copy()
    config_dir = root / ".tmp/qgis-profile-maritime"
    local_app_data = root / ".tmp/qgis-localappdata-maritime"
    matplotlib_cache = root / ".tmp/matplotlib-maritime"
    for directory in (config_dir, local_app_data, matplotlib_cache):
        directory.mkdir(parents=True, exist_ok=True)
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
    script_args = [
        str(root / "scripts/build_maritime_qgis.py"),
        "--spec",
        str(prepared.spec_path),
    ]
    subprocess.run(_qgis_command(root, script_args), cwd=root, env=environment, check=True)
    elapsed = time.perf_counter() - started
    timing_path = prepared.package_dir / "metadata" / "build-timing.json"
    timing_path.write_text(
        json.dumps(
            {
                "build_id": build_id,
                "elapsed_seconds": round(elapsed, 3),
                "scope": "prepare public evidence package and render/reopen with QGIS",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    qgis_project = (
        prepared.package_dir
        / "project"
        / f"MGRB_{request.area.replace('-', '_')}.qgz"
    )
    return MaritimeBuildResult(build_id, prepared.package_dir, qgis_project, elapsed)
