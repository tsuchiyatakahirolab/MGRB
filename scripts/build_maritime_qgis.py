#!/usr/bin/env python3
"""Build and validate a portable MGRB maritime research workspace with PyQGIS."""

from __future__ import annotations

import argparse
import copy
import gc
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # type: ignore
    Qgis,
    QgsApplication,
    QgsColorRampShader,
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
    QgsRasterShader,
    QgsRectangle,
    QgsSimpleLineCallout,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
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
        "outline_width": "0.42" if uncertain else "0.22",
        "size": "3.0" if uncertain else "2.4",
    }
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(properties)))


def _label_points(layer: QgsVectorLayer, color: str) -> None:
    settings = QgsPalLayerSettings()
    settings.fieldName = (
        "CASE "
        "WHEN \"actor_type\" = 'CCG' THEN replace(\"vessel_name\", 'China Coast Guard', 'CCG') "
        'WHEN "actor_type" = \'RESEARCH_SURVEY\' THEN "vessel_name" '
        'WHEN "actor_type" = \'FISHING\' THEN "vessel_name" '
        'ELSE "vessel_name" END'
    )
    settings.isExpression = True
    settings.enabled = True
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.dist = 2.2
    settings.priority = 9
    settings.obstacle = True
    text = QgsTextFormat()
    text.setFont(QFont(carto.FONT_FAMILY, 7))
    text.setSize(7)
    text.setColor(QColor(color))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.55)
    buffer.setColor(QColor("#f7f5ef"))
    text.setBuffer(buffer)
    settings.setFormat(text)
    callout = QgsSimpleLineCallout()
    callout.setEnabled(True)
    callout.setMinimumLength(1.5)
    callout.setMinimumLengthUnit(QgsUnitTypes.RenderMillimeters)
    callout.setLineSymbol(
        QgsLineSymbol.createSimple(
            {"line_color": color, "line_width": "0.18", "line_style": "solid"}
        )
    )
    settings.setCallout(callout)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _label_track(layer: QgsVectorLayer, color: str) -> None:
    settings = QgsPalLayerSettings()
    settings.fieldName = "'Xue Long - observed public cruise track'"
    settings.isExpression = True
    settings.enabled = True
    settings.placement = QgsPalLayerSettings.Curved
    settings.priority = 8
    text = QgsTextFormat()
    text.setFont(QFont(carto.FONT_FAMILY, 7))
    text.setSize(7)
    text.setColor(QColor(color))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.5)
    buffer.setColor(QColor("#f7f5ef"))
    text.setBuffer(buffer)
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _style_orientation_labels(layer: QgsVectorLayer, *, media: bool) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "transparent", "outline_style": "no", "size": "0"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.fieldName = "name"
    settings.enabled = True
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.priority = 4 if media else 2
    text = QgsTextFormat()
    text.setFont(QFont(carto.FONT_FAMILY, 11 if media else 7))
    text.setSize(11 if media else 7)
    text.setColor(QColor("#4b5960"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.5 if media else 0.35)
    buffer.setColor(QColor("#f7f5ef"))
    text.setBuffer(buffer)
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _style_traffic_density(layer: QgsRasterLayer) -> None:
    statistics = layer.dataProvider().bandStatistics(1)
    maximum = max(float(statistics.maximumValue), 1.0)
    shader_function = QgsColorRampShader()
    shader_function.setColorRampType(QgsColorRampShader.Interpolated)
    transparent = QColor("#8fa3ad")
    transparent.setAlpha(0)
    lower = QColor("#9aadb3")
    lower.setAlpha(55)
    common = QColor("#6f8d96")
    common.setAlpha(95)
    highest = QColor("#405f69")
    highest.setAlpha(135)
    shader_function.setColorRampItemList(
        [
            QgsColorRampShader.ColorRampItem(0.0, transparent, "No recorded density"),
            QgsColorRampShader.ColorRampItem(maximum * 0.72, transparent, "Lower"),
            QgsColorRampShader.ColorRampItem(maximum * 0.82, lower, "Moderate"),
            QgsColorRampShader.ColorRampItem(maximum * 0.92, common, "Common corridor"),
            QgsColorRampShader.ColorRampItem(maximum, highest, "Highest"),
        ]
    )
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_function)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.setOpacity(0.20)


def _line_style(
    layer: QgsVectorLayer,
    color: str,
    segment_type: str,
    *,
    width: str | None = None,
) -> None:
    line_style = {
        "OBSERVED_TRACK": "solid",
        "SHORT_INTERPOLATION": "dash dot",
        "INFERRED_CONNECTION": "dash",
    }[segment_type]
    width = width or ("0.85" if segment_type == "OBSERVED_TRACK" else "0.60")
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
            archive.read(name) for name in archive.namelist() if name.endswith((".qgs", ".xml"))
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
        f"\"actor_type\" = '{actor}' AND \"segment_type\" = 'OBSERVED_TRACK'",
    )
    _line_style(observed, color, "OBSERVED_TRACK")
    if actor == "RESEARCH_SURVEY":
        _label_track(observed, color)
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
            f"\"actor_type\" = '{actor}' AND \"source_type\" = 'OFFICIAL_OBSERVATION' "
            "AND coalesce(\"position_confidence\", 'UNKNOWN') <> 'LOW'"
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
        f"\"actor_type\" = '{actor}' AND \"segment_type\" = 'INFERRED_CONNECTION'",
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
    if layer.name() == "Observed Tracks":
        return f"{actor_name} observed track"
    if layer.name() == "Official Observations":
        return f"{actor_name} official point"
    return layer.name()


def _legend_layer_has_evidence(layer: QgsVectorLayer, evidence: dict) -> bool:
    subset = layer.subsetString()
    actor = next(
        (candidate for candidate in ACTOR_COLORS if f"'{candidate}'" in subset),
        None,
    )
    if actor is None:
        if layer.name() == "Observed Tracks":
            return int(evidence.get("segment_types", {}).get("OBSERVED_TRACK", 0)) > 0
        if layer.name() == "Inferred Segments":
            return int(evidence.get("segment_types", {}).get("INFERRED_CONNECTION", 0)) > 0
        if layer.name() == "Official Observations":
            return int(evidence.get("evidence_methods", {}).get("OFFICIAL_OBSERVATION", 0)) > 0
        return layer.featureCount() > 0
    if layer.name() == "Official Observations":
        return int(evidence.get("actor_observation_counts", {}).get(actor, 0)) > 0
    if layer.name() == "Inferred Segments":
        key = f"{actor}:INFERRED_CONNECTION"
        return int(evidence.get("actor_segment_counts", {}).get(key, 0)) > 0
    if layer.name() == "Observed Tracks":
        key = f"{actor}:OBSERVED_TRACK"
        return int(evidence.get("actor_segment_counts", {}).get(key, 0)) > 0
    return True


def build(spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    package = spec_path.parents[1]
    build_manifest = package / spec["files"]["build_manifest"]
    source_manifest = package / spec["files"]["source_manifest"]
    style_manifest = package / spec["files"]["style_manifest"]
    build_data = spec["build"]
    selected_state = spec.get("selected_state", {})
    enabled_maritime = set(selected_state.get("maritime_layers", ()))
    background_id = selected_state.get("background", "bathymetry")
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
    product_mode = bool(build_data.get("product_mode", False))
    if product_mode:
        root_groups = {
            name: root.addGroup(name)
            for name in (
                "01 BASE",
                "02 MARITIME JURISDICTION",
                "03 USER / VESSEL DATA",
                "04 OFFICIAL / OTHER OBSERVATIONS",
                "05 EVENTS",
                "06 INFRASTRUCTURE / CONTEXT",
                "07 ANALYTIC / OPTIONAL",
            )
        }
        user_group = root_groups["03 USER / VESSEL DATA"]
        groups = {
            "01 BASE": root_groups["01 BASE"],
            "02 MARITIME JURISDICTION": root_groups["02 MARITIME JURISDICTION"],
            "03 PLAN": user_group.addGroup("PLAN"),
            "04 CHINA COAST GUARD": user_group.addGroup("CCG"),
            "05 RESEARCH / SURVEY VESSELS": user_group.addGroup("RESEARCH / SURVEY"),
            "06 CHINESE FISHING": user_group.addGroup("FISHING / OTHER"),
            "07 EVENTS & ANNOTATIONS": root_groups["05 EVENTS"],
            "08 OPTIONAL / ANALYTIC": root_groups["07 ANALYTIC / OPTIONAL"],
        }
    else:
        root_groups = {
            name: root.addGroup(name)
            for name in (
                "01 BASE",
                "02 MARITIME JURISDICTION",
                "03 PLAN",
                "04 CHINA COAST GUARD",
                "05 RESEARCH / SURVEY VESSELS",
                "06 CHINESE FISHING",
                "07 EVENTS & ANNOTATIONS",
                "08 OPTIONAL / ANALYTIC",
            )
        }
        groups = root_groups

    bathy = QgsRasterLayer(str(files["bathymetry"]), "Bathymetry")
    if not bathy.isValid():
        raise RuntimeError(f"Invalid bathymetry: {files['bathymetry']}")
    carto._style_raster(bathy, spec["theme"], spec["cartographic_profile"])
    bathy.setOpacity(min(bathy.opacity(), 0.66))
    land = _layer(project, groups["01 BASE"], files["base_gpkg"], "land", "Land")
    carto._style_land(land, spec["theme"])
    coast = _layer(project, groups["01 BASE"], files["base_gpkg"], "coastline", "Coastline")
    carto._style_line(coast, "#4c5558", 0.22)
    project.addMapLayer(bathy, False)
    groups["01 BASE"].addLayer(bathy)
    _set_visibility(groups["01 BASE"], bathy, background_id != "none")
    traffic = None
    if spec["availability"]["normal_traffic_density"]:
        traffic = QgsRasterLayer(str(files["traffic_density"]), "Normal Traffic Density")
        if not traffic.isValid():
            raise RuntimeError("Cached traffic density raster is invalid")
        _style_traffic_density(traffic)
        project.addMapLayer(traffic, False)
        groups["01 BASE"].insertLayer(2, traffic)
    else:
        groups["08 OPTIONAL / ANALYTIC"].addGroup("Normal Traffic Density [NOT CACHED]")

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
    continental = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["maritime_gpkg"],
        "continental_shelf",
        "Continental Shelf Reference",
    )
    median = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["maritime_gpkg"],
        "computed_median",
        "Computed Median / Equidistance Reference",
    )
    custom_boundary = _layer(
        project,
        groups["02 MARITIME JURISDICTION"],
        files["maritime_gpkg"],
        "custom_boundary",
        "Custom Boundary Layer",
    )
    for boundary, style, width in (
        (territorial, "solid", "0.22"),
        (contiguous, "dash dot", "0.18"),
        (eez, "dash", "0.16"),
        (other, "dot", "0.14"),
        (continental, "dash dot", "0.16"),
        (median, "dash", "0.18"),
        (custom_boundary, "solid", "0.18"),
    ):
        _boundary_style(boundary, "#55656d", width, style)
    boundary_visibility = {
        territorial.id(): (
            "territorial_sea" in enabled_maritime and territorial.featureCount() > 0
        ),
        contiguous.id(): ("contiguous_zone" in enabled_maritime and contiguous.featureCount() > 0),
        eez.id(): "eez_reference" in enabled_maritime and eez.featureCount() > 0,
        other.id(): "maritime_boundary" in enabled_maritime and other.featureCount() > 0,
        continental.id(): (
            "continental_shelf" in enabled_maritime and continental.featureCount() > 0
        ),
        median.id(): "computed_median" in enabled_maritime and median.featureCount() > 0,
        custom_boundary.id(): (
            "custom_boundary" in enabled_maritime and custom_boundary.featureCount() > 0
        ),
    }
    for boundary in (territorial, contiguous, eez, other, continental, median, custom_boundary):
        _set_visibility(
            groups["02 MARITIME JURISDICTION"],
            boundary,
            boundary_visibility[boundary.id()],
        )

    evidence_layers: list[QgsVectorLayer] = []
    product_evidence_layers: list[QgsVectorLayer] = []
    if product_mode:
        generic_positions = _layer(
            project,
            root_groups["03 USER / VESSEL DATA"],
            files["observations_gpkg"],
            "observations",
            "Position Points",
            "\"source_type\" IN ('USER_SUPPLIED', 'AIS', 'PUBLIC_TRACK')",
        )
        _point_style(generic_positions, "#b44732")
        generic_tracks = _layer(
            project,
            root_groups["03 USER / VESSEL DATA"],
            files["tracks_gpkg"],
            "track_segments",
            "Observed Tracks",
            "\"segment_type\" = 'OBSERVED_TRACK'",
        )
        _line_style(generic_tracks, "#b44732", "OBSERVED_TRACK", width="0.45")
        generic_inferred = _layer(
            project,
            root_groups["04 OFFICIAL / OTHER OBSERVATIONS"],
            files["tracks_gpkg"],
            "track_segments",
            "Inferred Segments",
            "\"segment_type\" = 'INFERRED_CONNECTION'",
        )
        _line_style(generic_inferred, "#555555", "INFERRED_CONNECTION", width="0.35")
        generic_official = _layer(
            project,
            root_groups["04 OFFICIAL / OTHER OBSERVATIONS"],
            files["observations_gpkg"],
            "observations",
            "Official Observations",
            "\"source_type\" = 'OFFICIAL_OBSERVATION'",
        )
        _point_style(generic_official, "#555555")
        product_evidence_layers.extend(
            (generic_tracks, generic_positions, generic_inferred, generic_official)
        )
        evidence_layers.extend(product_evidence_layers)
        _set_visibility(
            root_groups["03 USER / VESSEL DATA"],
            generic_positions,
            generic_tracks.featureCount() == 0,
        )
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
        "\"actor_type\" = 'MARITIME_MILITIA'",
    )
    _point_style(militia, ACTOR_COLORS["MARITIME_MILITIA"])
    _set_visibility(groups["06 CHINESE FISHING"], militia, False)

    uncertain = _layer(
        project,
        groups["03 PLAN"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        "\"actor_type\" = 'PLAN' AND \"position_confidence\" = 'LOW'",
    )
    _point_style(uncertain, ACTOR_COLORS["PLAN"], uncertain=True)
    _label_points(uncertain, ACTOR_COLORS["PLAN"])
    ccg_uncertain = _layer(
        project,
        groups["04 CHINA COAST GUARD"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        "\"actor_type\" = 'CCG' AND \"position_confidence\" = 'LOW'",
    )
    _point_style(ccg_uncertain, ACTOR_COLORS["CCG"], uncertain=True)
    _label_points(ccg_uncertain, ACTOR_COLORS["CCG"])
    research_uncertain = _layer(
        project,
        groups["05 RESEARCH / SURVEY VESSELS"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        "\"actor_type\" = 'RESEARCH_SURVEY' AND \"position_confidence\" = 'LOW'",
    )
    _point_style(research_uncertain, ACTOR_COLORS["RESEARCH_SURVEY"], uncertain=True)
    _label_points(research_uncertain, ACTOR_COLORS["RESEARCH_SURVEY"])
    fishing_uncertain = _layer(
        project,
        groups["06 CHINESE FISHING"],
        files["observations_gpkg"],
        "observations",
        "Uncertain Detections",
        "\"actor_type\" = 'FISHING' AND \"position_confidence\" = 'LOW'",
    )
    _point_style(fishing_uncertain, ACTOR_COLORS["FISHING"], uncertain=True)
    _label_points(fishing_uncertain, ACTOR_COLORS["FISHING"])

    if product_mode:
        evidence_layers = product_evidence_layers

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
    paper_orientation = _layer(
        project,
        groups["07 EVENTS & ANNOTATIONS"],
        files["context_gpkg"],
        "orientation_labels",
        "Geographic Orientation - Paper",
        '"paper_visible" = 1',
    )
    _style_orientation_labels(paper_orientation, media=False)
    media_orientation = _layer(
        project,
        groups["07 EVENTS & ANNOTATIONS"],
        files["context_gpkg"],
        "orientation_labels",
        "Geographic Orientation - Media",
        '"media_visible" = 1',
    )
    _style_orientation_labels(media_orientation, media=True)
    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], media_orientation, False)
    groups["08 OPTIONAL / ANALYTIC"].addGroup("Additional user layers")

    extent = carto._extent_from_bbox(
        project,
        spec["region"]["bbox"],
        crs,
        spec["region"].get("longitude_convention", "180"),
    )
    extent = _fit_extent(extent, spec["layout"]["map_mm"])
    source_manifest_data = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_ids = {str(item.get("source_id")) for item in source_manifest_data["sources"]}
    source_names = ["GEBCO 2026"]
    if "pangaea_xue_long_2012" in source_ids:
        source_names.append("PANGAEA 891818 + World Bank shipping density")
    elif spec["availability"]["normal_traffic_density"]:
        source_names.append("World Bank shipping density + official public records")
    else:
        source_names.append("official public records; full sources in manifest")

    context_entries = []
    for boundary, label in (
        (territorial, "Territorial Sea reference"),
        (eez, "EEZ / reference EEZ"),
        (other, "Other maritime boundary"),
        (continental, "Continental shelf reference"),
        (median, "Computed median/equidistance reference"),
        (custom_boundary, "Custom boundary layer"),
    ):
        if boundary_visibility[boundary.id()] and boundary.featureCount() > 0:
            context_entries.append((boundary, label))
    evidence_entries = [
        (layer, _legend_label(layer))
        for layer in evidence_layers
        if layer.name() in {"Observed Tracks", "Official Observations", "Inferred Segments"}
        and _legend_layer_has_evidence(layer, build_data["evidence"])
    ]
    uncertain_candidates = [uncertain, ccg_uncertain, research_uncertain, fishing_uncertain]
    uncertain_for_legend = next(
        (layer for layer in uncertain_candidates if layer.featureCount() > 0), None
    )
    if uncertain_for_legend is not None:
        evidence_entries.insert(0, (uncertain_for_legend, "Lower-confidence point"))
    legend_sections = []
    if context_entries:
        legend_sections.append(("MARITIME CONTEXT", context_entries))
    if evidence_entries:
        legend_sections.append(("VESSEL / EVIDENCE", evidence_entries))
    legend_layers = [layer for _, entries in legend_sections for layer, _ in entries]

    paper_spec = copy.deepcopy(spec)
    paper_spec["build"]["layout_profile"] = "MGRB Paper"
    paper_spec["build"]["visible_footer"] = bool(build_data.get("visible_footer", True))
    paper_spec["layout_title"] = spec["region"]["purpose"]
    paper_spec["layout_subtitle"] = ""
    paper_spec["legend_title"] = "LEGEND"
    legend_row_count = sum(len(entries) + 1 for _, entries in legend_sections)
    compact_legend_height = max(18.0, min(40.0, 9.0 + legend_row_count * 4.8))
    paper_spec["layout"]["legend_mm"] = [38.0, compact_legend_height]
    paper = carto._build_layout(
        project,
        paper_spec,
        extent,
        crs,
        source_names,
        legend_layers,
        legend_sections=legend_sections,
    )

    media_spec = copy.deepcopy(spec)
    media_spec["build"]["layout_profile"] = "MGRB Media Editorial"
    media_spec["layout_title"] = spec["region"].get("media_title") or spec["region"]["title"]
    media_spec["layout_subtitle"] = spec["region"].get("media_subtitle") or ""
    media_geometry = {
        "portrait": ([180.0, 225.0], [8.0, 19.0, 164.0, 194.0]),
        "square": ([220.0, 200.0], [8.0, 19.0, 204.0, 169.0]),
        "landscape": ([320.0, 180.0], [8.0, 19.0, 304.0, 149.0]),
    }
    media_page, media_map = media_geometry[spec["layout"]["orientation"]]
    media_spec["layout"] = {
        **spec["layout"],
        "page_mm": media_page,
        "map_mm": media_map,
        "title_pt": 16,
        "subtitle_pt": 8,
        "footer_pt": 5,
        "legend_mm": [42.0, min(42.0, compact_legend_height + 2.0)],
    }
    media_spec["legend_title"] = "LEGEND"
    media_extent = _fit_extent(
        carto._extent_from_bbox(project, spec["region"]["bbox"], crs, "180"),
        media_spec["layout"]["map_mm"],
    )
    media = carto._build_layout(
        project,
        media_spec,
        media_extent,
        crs,
        source_names,
        legend_layers,
        legend_sections=legend_sections,
    )
    paper_scale_bar = paper.itemById("MGRB Scale Bar")
    media_scale_bar = media.itemById("MGRB Scale Bar")
    scale_bar_qa = {
        "paper_unit_label": paper_scale_bar.unitLabel(),
        "paper_interval_km": paper_scale_bar.unitsPerSegment(),
        "paper_segments": paper_scale_bar.numberOfSegments(),
        "media_unit_label": media_scale_bar.unitLabel(),
        "media_interval_km": media_scale_bar.unitsPerSegment(),
        "media_segments": media_scale_bar.numberOfSegments(),
    }
    scale_bar_qa["passed"] = (
        scale_bar_qa["paper_unit_label"] == "km"
        and scale_bar_qa["media_unit_label"] == "km"
        and scale_bar_qa["paper_segments"] == 2
        and scale_bar_qa["media_segments"] == 2
        and scale_bar_qa["paper_interval_km"] < 1000
        and scale_bar_qa["media_interval_km"] < 1000
    )
    if not scale_bar_qa["passed"]:
        raise RuntimeError(f"Human-readable kilometre scale-bar QA failed: {scale_bar_qa}")

    context_legend_qa = {
        "visible_context_layers": [label for _, label in context_entries],
        "legend_context_layers": [label for _, label in context_entries],
        "hidden_context_layers": [
            layer.name()
            for layer in (
                territorial,
                contiguous,
                eez,
                other,
                continental,
                median,
                custom_boundary,
            )
            if not boundary_visibility[layer.id()]
        ],
    }
    context_legend_qa["passed"] = (
        context_legend_qa["visible_context_layers"] == context_legend_qa["legend_context_layers"]
    )
    profile_distinction_qa = {
        "paper_title": paper_spec["layout_title"],
        "media_title": media_spec["layout_title"],
        "media_subtitle": media_spec["layout_subtitle"],
        "paper_title_pt": paper_spec["layout"]["title_pt"],
        "media_title_pt": media_spec["layout"]["title_pt"],
        "paper_orientation_labels": sum(
            bool(label.get("paper", True)) for label in spec["region"].get("orientation_labels", [])
        ),
        "media_orientation_labels": sum(
            bool(label.get("media", True)) for label in spec["region"].get("orientation_labels", [])
        ),
    }
    profile_distinction_qa["passed"] = (
        profile_distinction_qa["paper_title"] != profile_distinction_qa["media_title"]
        and bool(profile_distinction_qa["media_subtitle"])
        and profile_distinction_qa["media_title_pt"] > profile_distinction_qa["paper_title_pt"]
        and profile_distinction_qa["media_orientation_labels"]
        >= profile_distinction_qa["paper_orientation_labels"]
    )
    if not profile_distinction_qa["passed"]:
        raise RuntimeError(f"Paper/media profile distinction QA failed: {profile_distinction_qa}")

    official_style_layer = product_evidence_layers[3] if product_mode else evidence_layers[1]
    inferred_style_layer = product_evidence_layers[2] if product_mode else evidence_layers[2]
    for style_name, style_layer in (
        ("bathymetry-overlay-quiet.qml", bathy),
        ("official-observation.qml", official_style_layer),
        ("inferred-segment.qml", inferred_style_layer),
        ("uncertain-detection.qml", uncertain),
    ):
        style_layer.saveNamedStyle(str(package / "styles" / style_name))

    if product_mode:
        actor_group_map = {
            "PLAN": groups["03 PLAN"],
            "CCG": groups["04 CHINA COAST GUARD"],
            "RESEARCH_SURVEY": groups["05 RESEARCH / SURVEY VESSELS"],
            "FISHING": groups["06 CHINESE FISHING"],
        }
        for actor_group in actor_group_map.values():
            root_groups["03 USER / VESSEL DATA"].removeChildNode(actor_group)

    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], paper_orientation, True)
    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], media_orientation, False)
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
        "journal_width_png": exports / "paper_map_journal_85mm.png",
    }
    _export_layout(paper, outputs["paper_png"], "png", 300)
    _export_layout(paper, outputs["paper_pdf"], "pdf", 300)
    _export_layout(paper, outputs["paper_svg"], "svg", 300)
    journal_image = QImage(str(outputs["paper_png"]))
    journal_image = journal_image.scaledToWidth(1004)
    if not journal_image.save(str(outputs["journal_width_png"]), "PNG"):
        raise RuntimeError("Failed to create 85 mm journal-width preview")
    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], paper_orientation, False)
    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], media_orientation, True)
    _export_layout(media, outputs["media_png"], "png", 180)
    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], paper_orientation, True)
    _set_visibility(groups["07 EVENTS & ANNOTATIONS"], media_orientation, False)
    for output in outputs.values():
        _embed_lineage(output, build_data)

    paper_qa = _tofu_qa(outputs["paper_png"])
    media_qa = _tofu_qa(outputs["media_png"])
    journal_qa = _tofu_qa(outputs["journal_width_png"])
    if not paper_qa["passed"] or not media_qa["passed"] or not journal_qa["passed"]:
        raise RuntimeError(f"Missing-glyph/tofu QA failed: {paper_qa}, {media_qa}, {journal_qa}")
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
        spec["region"].get("longitude_convention", "180"),
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
        spec["region"].get("longitude_convention", "180"),
        spec["build"]["cartographic_profile"],
    )
    if not media_raster_qa["passed"]:
        raise RuntimeError(f"Media raster coverage QA failed: {media_raster_qa}")
    traffic_raster_qa = None
    traffic_media_raster_qa = None
    if traffic is not None:
        traffic_bbox = carto._raster_bbox(files["traffic_density"])
        traffic_raster_qa = carto._raster_coverage_qa(
            project,
            paper.referenceMap().extent(),
            crs,
            spec["region"]["bbox"],
            traffic_bbox,
            spec["region"].get("longitude_convention", "180"),
            spec["build"]["cartographic_profile"],
        )
        traffic_media_raster_qa = carto._raster_coverage_qa(
            project,
            media.referenceMap().extent(),
            crs,
            spec["region"]["bbox"],
            traffic_bbox,
            spec["region"].get("longitude_convention", "180"),
            spec["build"]["cartographic_profile"],
        )
        if not traffic_raster_qa["passed"] or not traffic_media_raster_qa["passed"]:
            raise RuntimeError(
                "Traffic-density raster coverage QA failed: "
                f"{traffic_raster_qa}, {traffic_media_raster_qa}"
            )

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
    expected_groups = list(root_groups)
    if group_names != expected_groups:
        raise RuntimeError(f"Unexpected QGIS layer tree: {group_names}")
    reopened.clear()
    del reopened
    gc.collect()
    QgsApplication.processEvents()

    portable_root = ROOT / ".tmp" / "portability" / build_data["build_id"]
    if portable_root.exists():
        shutil.rmtree(portable_root)
    shutil.copytree(package, portable_root)
    portable_project = portable_root / "project" / qgz.name
    portable = QgsProject()
    portable_ok = portable.read(str(portable_project))
    portable_invalid = sorted(
        layer.name() for layer in portable.mapLayers().values() if not layer.isValid()
    )
    portable.clear()
    del portable
    gc.collect()
    QgsApplication.processEvents()
    shutil.rmtree(portable_root)
    if not portable_ok or portable_invalid:
        raise RuntimeError(f"Portable-copy reopen failed: {portable_invalid}")

    layer_count = len(project.mapLayers())
    evidence_dominates_basemap = bathy.opacity() <= 0.66
    project.clear()
    gc.collect()
    QgsApplication.processEvents()

    # Reopening a GeoPackage may update internal provider metadata on some GDAL/QGIS
    # combinations. Finalize lineage only after every provider has been released.
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
        raise RuntimeError(f"Final lineage verification failed: {verification}")

    validation = {
        "schema": "mgrb-maritime-qgis-validation-1.0",
        "build_id": build_data["build_id"],
        "qgis_version": Qgis.QGIS_VERSION,
        "project": qgz.relative_to(package).as_posix(),
        "layer_groups": group_names,
        "layer_count": layer_count,
        "exports": {key: value.relative_to(package).as_posix() for key, value in outputs.items()},
        "artifact_verification": verification,
        "relative_paths": not _project_has_repo_path(qgz),
        "portable_copy_reopen": portable_ok and not portable_invalid,
        "visual_qa": {
            "bundled_font": carto.FONT_PREFLIGHT,
            "paper_text": paper_qa,
            "media_text": media_qa,
            "journal_width_text": journal_qa,
            "raster_coverage": raster_qa,
            "media_raster_coverage": media_raster_qa,
            "traffic_raster_coverage": traffic_raster_qa,
            "traffic_media_raster_coverage": traffic_media_raster_qa,
            "layout_geometry": layout_checks,
            "track_evidence_dominates_basemap": evidence_dominates_basemap,
            "scale_bar": scale_bar_qa,
            "context_legend": context_legend_qa,
            "paper_media_distinction": profile_distinction_qa,
            "inferred_entity_integrity": build_data["evidence"].get(
                "inferred_entity_integrity", False
            ),
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
