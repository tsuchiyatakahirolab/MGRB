from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BuildRequest:
    region: str
    profile: str
    theme: str
    output_root: Path
    build_id: str | None = None
    visible_footer: bool = True
    regions_config: Path | None = None


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
    background: str = "bathymetry"
    enabled_maritime_layers: tuple[str, ...] = ("eez_reference", "territorial_sea")
    field_maps: dict[str, dict[str, str]] | None = None
    input_kinds: dict[str, str] | None = None
    input_metadata: dict[str, dict[str, str]] | None = None
    context_layers: tuple[str, ...] = ()
    include_public_observations: bool = True
    product_mode: bool = False
    regions_config: Path | None = None
    visible_footer: bool = True
    requested_outputs: tuple[str, ...] = ("preview", "paper", "media", "qgis")


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
    if request.regions_config:
        prepare_command.extend(["--regions-config", str(request.regions_config)])
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
            background=request.background,
            enabled_maritime_layers=request.enabled_maritime_layers,
            field_maps=request.field_maps,
            input_kinds=request.input_kinds,
            input_metadata=request.input_metadata,
            context_layers=request.context_layers,
            include_public_observations=request.include_public_observations,
            product_mode=request.product_mode,
            regions_config=request.regions_config,
            visible_footer=request.visible_footer,
            requested_outputs=request.requested_outputs,
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
    qgis_project = prepared.package_dir / "project" / f"MGRB_{request.area.replace('-', '_')}.qgz"
    return MaritimeBuildResult(build_id, prepared.package_dir, qgis_project, elapsed)


def make_portable_zip(package_dir: Path) -> Path:
    """Create a deterministic-order portable archive beside a completed package."""
    from .firewall import assert_public_package

    assert_public_package(package_dir)
    archive = package_dir.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(package_dir.parent).as_posix())
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                output.writestr(info, path.read_bytes())
    return archive


def execute_product_build(
    spec,
    *,
    output_root: Path,
    repository_root: Path,
    build_id: str,
) -> tuple[MaritimeBuildResult, Path]:
    """Resolve product choices into the canonical maritime/QGIS build pipeline."""
    from .config import load_regions
    from .product import BACKGROUND_PRESETS, custom_region_defaults, safe_build_id

    root = repository_root.resolve()
    build_id = safe_build_id(build_id)
    spec.validate(root)
    regions_config = root / "config" / "regions.yml"
    area = spec.area
    if area == "custom":
        defaults = custom_region_defaults(spec.custom_extent)
        area = f"custom-{build_id}"
        payload = yaml.safe_load(regions_config.read_text(encoding="utf-8"))
        payload["regions"][area] = {
            "bbox_180": defaults["bbox"],
            "purpose": f"Custom research extent {defaults['bbox']}",
            "title": "Custom Maritime Research Area",
            "display_crs": defaults["display_crs"],
            "layout_scale": defaults["profile"],
            "profile": defaults["profile"],
            "gebco_stride": 4 if defaults["profile"] == "local" else 12,
            "research_preset": True,
            "base_region": area,
            "base_build_id": f"{area}-base",
            "context_sources": {
                "land": ["gshhg_2_3_7", "natural_earth_5_1_2"],
                "coastline": ["gshhg_2_3_7", "natural_earth_5_1_2"],
                "labels": ["natural_earth_5_1_2"],
            },
        }
        regions_config = root / ".tmp" / "product-config" / build_id / "regions.yml"
        regions_config.parent.mkdir(parents=True, exist_ok=True)
        regions_config.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    regions = load_regions(regions_config)
    region = regions[area]
    base_build_id = region.base_build_id or f"{area}-base"
    base_dir = root / "data" / "derived" / base_build_id
    if not (base_dir / "base.gpkg").exists() or not (base_dir / "bathymetry.tif").exists():
        background = BACKGROUND_PRESETS[spec.background]
        command = [
            sys.executable,
            str(root / "scripts" / "prepare_owner_review.py"),
            "--region",
            region.base_region or area,
            "--profile",
            region.profile,
            "--theme",
            str(background["theme"]),
            "--output-name",
            base_build_id,
            "--regions-config",
            str(regions_config),
        ]
        if not spec.visible_footer:
            command.append("--no-visible-footer")
        subprocess.run(command, cwd=root, check=True)

    request = MaritimeBuildRequest(
        area=area,
        output_root=output_root,
        build_id=build_id,
        start_date=date.fromisoformat(spec.start_date) if spec.start_date else None,
        end_date=date.fromisoformat(spec.end_date) if spec.end_date else None,
        actors=spec.actors,
        public_data=True,
        local_inputs=tuple(Path(path).resolve() for path in spec.input_files),
        live_sources=True,
        background=spec.background,
        enabled_maritime_layers=spec.maritime_layers,
        field_maps=spec.field_maps,
        input_kinds=spec.input_kinds,
        input_metadata=spec.input_metadata,
        context_layers=spec.context_layers,
        include_public_observations=spec.include_public_observations,
        product_mode=True,
        regions_config=regions_config,
        visible_footer=spec.visible_footer,
        requested_outputs=spec.outputs,
    )
    result = execute_maritime_build(request, root)
    archive = make_portable_zip(result.output)
    return result, archive
