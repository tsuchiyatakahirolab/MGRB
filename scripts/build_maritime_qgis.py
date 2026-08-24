#!/usr/bin/env python3
"""Build and validate a portable MGRB maritime research workspace with PyQGIS."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # type: ignore
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsExpressionContextUtils,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsProjectMetadata,
    QgsRasterLayer,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont, QImage  # type: ignore

from mgrb.cartography import layout_qa
from mgrb.render_qa import detect_tofu_blocks
from mgrb.verification import (
    verify_generated_file,
    write_artifact_sidecar,
    write_sha256sums,
)
from scripts import build_qgis_projects as carto

ROOT = Path(__file__).resolve().parents[1]
ACTOR_COLORS = {
    "PLAN": "#9e2f2f",
    "CCG": "#d07823",
    "RESEARCH_SURVEY": "#6d3d8f",
    "FISHING": "#237a57",
    "MARITIME_MILITIA": "#333333",
}


def _layer(
    project: QgsProject,
    group,
    path: Path,
    table: str,
    name: str,
    subset: str = "",
) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"{path}|layername={table}", name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Invalid layer {table} in {path}")
    if subset and not layer.setSubsetString(subset):
        raise RuntimeError(f"Invalid subset for {name}: {subset}")
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    return layer


def _point_style(layer: QgsVectorLayer, color: str, *, uncertain: bool = False) -> None:
    properties = {
        "name": "circle" if uncertain else "square",
        "color": "#ffffff" if uncertain else color,
        "outline_color": color,
        "outline_width": "0.65" if uncertain else "0.25",
        "size": "4.4" if uncertain else "3.1",
    }
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(properties)))


def _label_points(layer: QgsVectorLayer, color: str) -> None:
    settings = QgsPalLayerSettings()
    settings.fieldName = (
        "CASE "
        "WHEN \"actor_type\" = 'CCG' THEN replace(\"vessel_name\", 'China Coast Guard', 'CCG') "
        "WHEN \"actor_type\" = 'RESEARCH_SURVEY' THEN \"vessel_name\" "
        "WHEN \"actor_type\" = 'FISHING' THEN \"vessel_name\" "
        "ELSE \"vessel_name\" END"
    )
    settings.isExpression = True
    settings.enabled = True
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    text = QgsTextFormat()
    text.setFont(QFont(carto.FONT_FAMILY, 7))
    text.setSize(7)
    text.setColor(QColor(color))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("#f7f5ef"))
    text.setBuffer(buffer)
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _line_style(layer: QgsVectorLayer, color: str, segment_type: str) -> None:
    line_style = {
        "OBSERVED_TRACK": "solid",
        "SHORT_INTERPOLATION": "dash dot",
        "INFERRED_CONNECTION": "dash",
    }[segment_type]
    width = "0.85" if segment_type == "OBSERVED_TRACK" else "0.60"
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {"line_color": color, "line_width": width, "line_style": line_style}
            )
        )
    )


def _boundary_style(layer: QgsVectorLayer, color: str, width: str, style: str) -> None:
    if layer.geometryType() == Qgis.GeometryType.Polygon:
        layer.setRenderer(
            QgsSingleSymbolRenderer(
                QgsFillSymbol.createSimple(
                    {
                        "color": "transparent",
                        "style": "no",
                        "outline_color": color,
                        "outline_width": width,
                        "outline_style": style,
                    }
                )
            )
        )
        layer.setOpacity(0.48)
        return
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {"line_color": color, "line_width": width, "line_style": style}
            )
        )
    )
    layer.setOpacity(0.48)


def _set_visibility(group, layer: QgsVectorLayer, visible: bool) -> None:
    node = group.findLayer(layer.id())
    if node is not None:
        node.setItemVisibilityChecked(visible)


def _fit_extent(extent: QgsRectangle, map_mm: list[float]) -> QgsRectangle:
    aspect = float(map_mm[2]) / float(map_mm[3])
    if extent.width() / extent.height() > aspect:
        padding = (extent.width() / aspect - extent.height()) / 2.0
        return QgsRectangle(
            extent.xMinimum(),
            extent.yMinimum() - padding,
            extent.xMaximum(),
            extent.yMaximum() + padding,
        )
    padding = (extent.height() * aspect - extent.width()) / 2.0
    return QgsRectangle(
        extent.xMinimum() - padding,
        extent.yMinimum(),
        extent.xMaximum() + padding,
        extent.yMaximum(),
    )


def _project_has_repo_path(project_path: Path) -> bool:
    with zipfile.ZipFile(project_path) as archive:
        payload = b"\n".join(
            archive.read(name)
            for name in archive.namelist()
            if name.endswith((".qgs", ".xml"))
        ).decode("utf-8", errors="ignore")
    return str(ROOT).lower().replace("\\", "/") in payload.lower().replace("\\", "/")


def _export_layout(layout, path: Path, kind: str, dpi: int = 300) -> None:
    exporter = QgsLayoutExporter(layout)
    if kind == "png":
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi
        result = exporter.exportToImage(str(path), settings)
    elif kind == "pdf":
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.exportMetadata = True
        result = exporter.exportToPdf(str(path), settings)
    elif kind == "svg":
        settings = QgsLayoutExporter.SvgExportSettings()
        result = exporter.exportToSvg(str(path), settings)
    else:
        raise ValueError(kind)
    if result != QgsLayoutExporter.Success or not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"{kind.upper()} export failed for {path}: {result}")


def _embed_lineage(path: Path, build: dict) -> None:
    payload = json.dumps(build, sort_keys=True)
    if path.suffix.lower() == ".png":
        image = QImage(str(path))
        image.setText("MGRB-Lineage", payload)
        image.setText("Description", build["recommended_citation"])
        staged = path.with_name(path.stem + "-metadata.png")
        if not image.save(str(staged), "PNG"):
            raise RuntimeError(f"PNG metadata embedding failed: {path}")
        staged.replace(path)
    elif path.suffix.lower() == ".svg":
        tree = ElementTree.parse(path)
        metadata = ElementTree.Element("metadata", {"id": "mgrb-lineage"})
        metadata.text = payload
        tree.getroot().insert(0, metadata)
        tree.write(path, encoding="utf-8", xml_declaration=True)


def _tofu_qa(path: Path) -> dict:
    image = QImage(str(path)).convertToFormat(QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    pointer = image.bits()
    pointer.setsize(image.sizeInBytes())
    import numpy as np

    array = np.frombuffer(pointer, dtype=np.uint8).reshape((height, image.bytesPerLine()))
    rgb = array[:, : width * 3].reshape((height, width, 3)).copy()
    result = detect_tofu_blocks(rgb)
    result.update({"checked_file": path.name, "pixel_dimensions": [width, height]})
    return result


def _add_actor_layers(
    project: QgsProject,
    group,
    actor: str,
    observations: Path,
    tracks: Path,
    names: tuple[str, ...],
) -> list[QgsVectorLayer]:
    color = ACTOR_COLORS[actor]
    observed = _layer(
        project,
        group,
        tracks,
        "track_segments",
        names[0],
        f'"actor_type" = \'{actor}\' AND "segment_type" = \'OBSERVED_TRACK\'',
    )
    _line_style(observed, color, "OBSERVED_TRACK")
    middle_layers: list[QgsVectorLayer] = []
    for middle_name in names[1:-2]:
        placeholder = _layer(
            project,
            group,
            observations,
            "observations",
            middle_name,
            '"observation_id" IS NULL',
        )
        _point_style(placeholder, color)
        _set_visibility(group, placeholder, False)
        middle_layers.append(placeholder)
    official = _layer(
        project,
        group,
        observations,
        "observations",
        names[-2],
        (
            f'"actor_type" = \'{actor}\' AND "source_type" = \'OFFICIAL_OBSERVATION\''
        ),
    )
    _point_style(official, color)
    _label_points(official, color)
    inferred = _layer(
        project,
        group,
        tracks,
        "track_segments",
        names[-1],
        f'"actor_type" = \'{actor}\' AND "segment_type" = \'INFERRED_CONNECTION\'',
    )
    _line_style(inferred, color, "INFERRED_CONNECTION")
    return [observed, *middle_layers, official, inferred]


def _legend_label(layer: QgsVectorLayer) -> str:
    if layer.name() == "Uncertain Detections":
        return "Lower-confidence point"
    if layer.name() == "EEZ / Reference EEZ":
        return "EEZ / reference EEZ"
    subset = layer.subsetString()
    actor_name = next(
        (
            label
            for actor, label in (
                ("PLAN", "PLAN"),
                ("CCG", "CCG"),
                ("RESEARCH_SURVEY", "Research/survey"),
                ("FISHING", "Fishing"),
            )
            if f"'{actor}'" in subset
        ),
        "Evidence",
    )
    if layer.name() == "Inferred Segments":
        return f"{actor_name} inferred"
    if layer.name() == "Official Observations":
        return f"{actor_name} official point"
    return layer.name()


def build(spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    package = spec_path.parents[1]
    build_manifest = package / spec["files"]["build_manifest"]
    source_manifest = package / spec["files"]["source_manifest"]
    style_manifest = package / spec["files"]["style_manifest"]
    build_data = spec["build"]
    files = {key: package / value for key, value in spec["files"].items() if value}

    project = QgsProject.instance()
    project.clear()
    qgz = package / "project" / f"MGRB_{spec['region']['name'].replace('-', '_')}.qgz"
    project.setFileName(str(qgz))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setTitle(f"MGRB maritime research | {build_data['build_id']}")
    metadata = QgsProjectMetadata()
    metadata.setTitle(f"{build_data['formal_name']} — {spec['region']['title']}")
    metadata.setAbstract(build_data["recommended_citation"])
    metadata.setAuthor("Maritime Geospatial Research Base (MGRB)")
    metadata.setKeywords(
        {
            "MGRB lineage": [
                f"version:{build_data['mgrb_version']}",
                f"commit:{build_data.get('git_commit') or 'unknown'}",
                f"build:{build_data['build_id']}",
                f"theme-sha256:{build_data['theme']['palette_sha256']}",
                f"source-manifest-sha256:{build_data['source_manifest_sha256']}",
            ]
        }
    )
    project.setMetadata(metadata)
    crs = QgsCoordinateReferenceSystem()
    if not crs.createFromProj(spec["region"]["display_crs"]):
        raise RuntimeError(f"Invalid preset CRS: {spec['region']['display_crs']}")
    project.setCrs(crs)
    project.setEllipsoid("WGS84")
    for key, value in {
        "mgrb_version": build_data["mgrb_version"],
        "mgrb_commit": build_data.get("git_commit") or "unknown",
        "mgrb_build_id": build_data["build_id"],
        "mgrb_region": build_data["region_profile"],
        "mgrb_theme_sha256": build_data["theme"]["palette_sha256"],
        "mgrb_source_manifest_sha256": build_data["source_manifest_sha256"],
    }.items():
        QgsExpressionContextUtils.setProjectVariable(project, key, value)
    project.writeEntry("MGRB", "build_manifest", build_manifest.read_text(encoding="utf-8"))
    project.writeEntry("MGRB", "source_manifest", source_manifest.read_text(encoding="utf-8"))
    project.writeEntry("MGRB", "style_manifest", style_manifest.read_text(encoding="utf-8"))

    root = project.layerTreeRoot()
    groups = {name: root.addGroup(name) for name in (
        "01 BASE",
        "02 MARITIME JURISDICTION",
        "03 PLAN",
        "04 CHINA COAST GUARD",
        "05 RESEARCH / SURVEY VESSELS",
        "06 CHINESE FISHING",
        "07 EVENTS & ANNOTATIONS",
        "08 OPTIONAL / ANALYTIC",
    )}

    bathy = QgsRasterLayer(str(files["bathymetry"]), "Bathymetry")
    if not bathy.isValid():
        raise RuntimeError(f"Invalid bathymetry: {files['bathymetry']}")
    carto._style_raster(bathy, spec["theme"], spec["cartographic_profile"])
    bathy.setOpacity(min(bathy.opacity(), 0.66))
    land = _layer(project, groups["01 BASE"], files["base_gpkg"], "land", "Land")
    carto._style_land(land, spec["theme"])
    coast = _layer(
        project, groups["01 BASE"], files["base_gpkg"], "coastline", "Coastline"
    )
    carto._style_line(coast, "#4c5558", 0.22)
    project.addMapLayer(bathy, False)
    groups["01 BASE"].addLayer(bathy)
    if spec["availability"]["normal_traffic_density"]:
        traffic = QgsRasterLayer(str(files["traffic_density"]), "Normal Traffic Density")
        if not traffic.isValid():
            raise RuntimeError("Cached traffic density raster is invalid")
        project.addMapLayer(traffic, False)
        groups["01 BASE"].addLayer(traffic)
        traffic.setOpacity(0.28)
    else:
        groups["01 BASE"].addGroup("Normal Traffic Density [NOT CACHED]")

    territorial = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["maritime_gpkg"],
        "territorial_sea",
        "Territorial Sea",
    )
    contiguous = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["maritime_gpkg"],
        "contiguous_zone",
        "Contiguous Zone",
    )
    eez = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["maritime_gpkg"],
        "eez_reference",
        "EEZ / Reference EEZ",
    )
    other = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["base_gpkg"],
        "maritime_boundaries",
        "Other Maritime Boundaries",
    )
    for boundary, style, width in (
        (territorial, "solid", "0.22"),
        (contiguous, "dash dot", "0.18"),
        (eez, "dash", "0.16"),
        (other, "dot", "0.14"),
    ):
        _boundary_style(boundary, "#55656d", width, style)

    evidence_layers: list[QgsVectorLayer] = []
    evidence_layers.extend(
        _add_actor_layers(
            project,
            groups["03 PLAN"],
            "PLAN",
            files["observations_gpkg"],
            files["tracks_gpkg"],
            ("Observed Tracks", "Official Observations", "Inferred Segments"),
        )
    )
    evidence_layers.extend(
        _add_actor_layers(
            project,
            groups["04 CHINA COAST GUARD"],
            "CCG",
            files["observations_gpkg"],
            files["tracks_gpkg"],
            ("Observed Tracks", "Official Observations", "Inferred Segments"),
        )
    )
    evidence_layers.extend(
        _add_actor_layers(
            project,
            groups["05 RESEARCH / SURVEY VESSELS"],
            "RESEARCH_SURVEY",
            files["observations_gpkg"],
            files["tracks_gpkg"],
            (
                "Observed Tracks",
                "Loitering / Survey Events",
                "Official Observations",
                "Inferred Segments",
            ),
        )
    )
    evidence_layers.extend(
        _add_actor_layers(
            project,
            groups["06 CHINESE FISHING"],
            "FISHING",
            files["observations_gpkg"],
            files["tracks_gpkg"],
            (
                "Observed Tracks",
                "Vessel Presence",
                "VIIRS Detections",
                "Fishing Events",
                "Official Observations",
                "Inferred Segments",
            ),
        )
    )
    militia = _layer(
        project,
        groups["06 CHINESE FISHING"],
        files["observations_gpkg"],
        "observations",
        "Documented Maritime Militia",
        '"actor_type" = \'MARITIME_MILITIA\'',
    )
    _point_style(militia, ACTOR_COLORS["MARITIME_MILITIA"])
    _set_visibility(groups["06 CHINESE FISHING"], militia, False)

    uncertain = _layer(
        project,
        groups["03 PLAN"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        '"actor_type" = \'PLAN\' AND "position_confidence" = \'LOW\'',
    )
    _point_style(uncertain, ACTOR_COLORS["PLAN"], uncertain=True)
    ccg_uncertain = _layer(
        project,
        groups["04 CHINA COAST GUARD"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        '"actor_type" = \'CCG\' AND "position_confidence" = \'LOW\'',
    )
    _point_style(ccg_uncertain, ACTOR_COLORS["CCG"], uncertain=True)
    research_uncertain = _layer(
        project,
        groups["05 RESEARCH / SURVEY VESSELS"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        '"actor_type" = \'RESEARCH_SURVEY\' AND "position_confidence" = \'LOW\'',
    )
    _point_style(research_uncertain, ACTOR_COLORS["RESEARCH_SURVEY"], uncertain=True)
    fishing_uncertain = _layer(
        project,
        groups["06 CHINESE FISHING"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        '"actor_type" = \'FISHING\' AND "position_confidence" = \'LOW\'',
    )
    _point_style(fishing_uncertain, ACTOR_COLORS["FISHING"], uncertain=True)

    for name in ("Encounters", "Port Visits", "AIS Gaps", "User Notes"):
        placeholder = _layer(
            project,
            groups["07 EVENTS & ANNOTATIONS"],
            files["events_gpkg"],
            "events",
            name,
            '"event_id" IS NULL',
        )
        _point_style(placeholder, "#555555")
        _set_visibility(groups["07 EVENTS & ANNOTATIONS"], placeholder, False)
    groups["08 OPTIONAL / ANALYTIC"].addGroup("Additional user layers")

    extent = carto._extent_from_bbox(
        project,
        spec["region"]["bbox"],
        crs,
        spec["region"].get("longitude_convention", "180"),
    )
    extent = _fit_extent(extent, spec["layout"]["map_mm"])
    source_manifest_data = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_names = [
        str(item.get("dataset") or item.get("source_id"))
        for item in source_manifest_data["sources"][:2]
    ]
    legend_layers = [
        uncertain,
        *[
            layer
            for layer in evidence_layers
            if layer.name() in {"Official Observations", "Inferred Segments"}
            and layer.featureCount() > 0
        ][:5],
    ]
    paper_spec = copy.deepcopy(spec)
    paper_spec["build"]["layout_profile"] = "MGRB Paper"
    paper_spec["build"]["visible_footer"] = True
    paper_spec["legend_title"] = "Evidence"
    paper_spec["legend_labels"] = [_legend_label(layer) for layer in legend_layers]
    paper_spec["layout"]["legend_mm"] = [38.0, 34.0]
    paper = carto._build_layout(project, paper_spec, extent, crs, source_names, legend_layers)

    media_spec = copy.deepcopy(spec)
    media_spec["build"]["layout_profile"] = "MGRB Media 16x9"
    media_spec["region"]["purpose"] = spec["region"]["title"]
    media_geometry = {
        "portrait": ([180.0, 225.0], [8.0, 12.0, 164.0, 203.0]),
        "square": ([220.0, 200.0], [8.0, 12.0, 204.0, 178.0]),
        "landscape": ([320.0, 180.0], [8.0, 12.0, 304.0, 158.0]),
    }
    media_page, media_map = media_geometry[spec["layout"]["orientation"]]
    media_spec["layout"] = {
        **spec["layout"],
        "page_mm": media_page,
        "map_mm": media_map,
        "title_pt": 13,
        "footer_pt": 5,
        "legend_mm": [38.0, 34.0],
    }
    media_spec["legend_title"] = "Evidence"
    media_spec["legend_labels"] = [_legend_label(layer) for layer in legend_layers]
    media_extent = _fit_extent(
        carto._extent_from_bbox(project, spec["region"]["bbox"], crs, "180"),
        media_spec["layout"]["map_mm"],
    )
    media = carto._build_layout(
        project, media_spec, media_extent, crs, source_names, legend_layers
    )

    for style_name, style_layer in (
        ("bathymetry-overlay-quiet.qml", bathy),
        ("official-observation.qml", evidence_layers[1]),
        ("inferred-segment.qml", evidence_layers[2]),
        ("uncertain-detection.qml", uncertain),
    ):
        style_layer.saveNamedStyle(str(package / "styles" / style_name))

    if not project.write(str(qgz)):
        raise RuntimeError(f"Failed to save QGIS project: {qgz}")
    if _project_has_repo_path(qgz):
        raise RuntimeError(f"QGIS project contains a repository-specific absolute path: {qgz}")

    exports = package / "exports"
    outputs = {
        "paper_png": exports / "paper_map.png",
        "paper_pdf": exports / "paper_map.pdf",
        "paper_svg": exports / "paper_map.svg",
        "media_png": exports / "media_map.png",
    }
    _export_layout(paper, outputs["paper_png"], "png", 300)
    _export_layout(paper, outputs["paper_pdf"], "pdf", 300)
    _export_layout(paper, outputs["paper_svg"], "svg", 300)
    _export_layout(media, outputs["media_png"], "png", 180)
    for output in outputs.values():
        _embed_lineage(output, build_data)

    paper_qa = _tofu_qa(outputs["paper_png"])
    media_qa = _tofu_qa(outputs["media_png"])
    if not paper_qa["passed"] or not media_qa["passed"]:
        raise RuntimeError(f"Missing-glyph/tofu QA failed: {paper_qa}, {media_qa}")
    layout_checks = layout_qa(spec["layout"], tuple(spec["region"]["bbox"]))
    if not layout_checks["orientation_is_adaptive"] or layout_checks["awkward_map_frame"]:
        raise RuntimeError(f"Adaptive layout QA failed: {layout_checks}")
    raster_bbox = carto._raster_bbox(files["bathymetry"])
    raster_qa = carto._raster_coverage_qa(
        project,
        paper.referenceMap().extent(),
        crs,
        spec["region"]["bbox"],
        raster_bbox,
        "180",
        spec["build"]["cartographic_profile"],
    )
    if not raster_qa["passed"]:
        raise RuntimeError(f"Raster coverage QA failed: {raster_qa}")
    media_raster_qa = carto._raster_coverage_qa(
        project,
        media.referenceMap().extent(),
        crs,
        spec["region"]["bbox"],
        raster_bbox,
        "180",
        spec["build"]["cartographic_profile"],
    )
    if not media_raster_qa["passed"]:
        raise RuntimeError(f"Media raster coverage QA failed: {media_raster_qa}")

    manifest_paths = [build_manifest, source_manifest, style_manifest]
    artifacts = [qgz, *outputs.values(), *files.values()]
    sidecars = [
        write_artifact_sidecar(artifact, build_manifest, source_manifest, style_manifest)
        for artifact in dict.fromkeys(artifacts)
        if artifact.is_file()
    ]
    write_sha256sums(
        [*dict.fromkeys(artifacts), *sidecars, *manifest_paths],
        package / "metadata" / "SHA256SUMS",
        package,
    )
    verification = {
        artifact.relative_to(package).as_posix(): verify_generated_file(artifact)["ok"]
        for artifact in [qgz, *outputs.values()]
    }
    if not all(verification.values()):
        raise RuntimeError(f"Lineage verification failed: {verification}")

    reopened = QgsProject()
    if not reopened.read(str(qgz)):
        raise RuntimeError(f"QGIS could not reopen generated project: {qgz}")
    group_names = [child.name() for child in reopened.layerTreeRoot().children()]
    expected_groups = list(groups)
    if group_names != expected_groups:
        raise RuntimeError(f"Unexpected QGIS layer tree: {group_names}")
    reopened.clear()

    portable_root = ROOT / ".tmp" / "portability" / build_data["build_id"]
    if portable_root.exists():
        shutil.rmtree(portable_root)
    shutil.copytree(package, portable_root)
    portable_project = portable_root / "project" / qgz.name
    portable = QgsProject()
    portable_ok = portable.read(str(portable_project))
    portable_invalid = sorted(layer.name() for layer in portable.mapLayers().values() if not layer.isValid())
    portable.clear()
    shutil.rmtree(portable_root)
    if not portable_ok or portable_invalid:
        raise RuntimeError(f"Portable-copy reopen failed: {portable_invalid}")

    validation = {
        "schema": "mgrb-maritime-qgis-validation-1.0",
        "build_id": build_data["build_id"],
        "qgis_version": Qgis.QGIS_VERSION,
        "project": qgz.relative_to(package).as_posix(),
        "layer_groups": group_names,
        "layer_count": len(project.mapLayers()),
        "exports": {key: value.relative_to(package).as_posix() for key, value in outputs.items()},
        "artifact_verification": verification,
        "relative_paths": not _project_has_repo_path(qgz),
        "portable_copy_reopen": portable_ok and not portable_invalid,
        "visual_qa": {
            "bundled_font": carto.FONT_PREFLIGHT,
            "paper_text": paper_qa,
            "media_text": media_qa,
            "raster_coverage": raster_qa,
            "media_raster_coverage": media_raster_qa,
            "layout_geometry": layout_checks,
            "track_evidence_dominates_basemap": bathy.opacity() <= 0.66,
        },
    }
    validation_path = package / "metadata" / "qgis-validation.json"
    validation_path.write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    application = carto._start_qgis()
    try:
        print(json.dumps(build(args.spec.resolve()), indent=2))
    finally:
        application.exitQgis()


if __name__ == "__main__":
    main()
