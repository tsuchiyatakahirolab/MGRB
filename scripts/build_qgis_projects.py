#!/usr/bin/env python3
"""Build, render, reopen, and validate MGRB projects with real PyQGIS."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from osgeo import gdal, ogr, osr  # type: ignore
from qgis.core import (  # type: ignore
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpressionContextUtils,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemMapGrid,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsProjectMetadata,
    QgsRasterLayer,
    QgsRasterShader,
    QgsRectangle,
    QgsRendererCategory,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import Qt  # type: ignore
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPainter  # type: ignore

from mgrb.verification import verify_generated_file, write_artifact_sidecar, write_sha256sums

ROOT = Path(__file__).resolve().parents[1]
if hasattr(Qt, "TransformationMode"):
    SMOOTH_TRANSFORMATION = Qt.TransformationMode.SmoothTransformation
    KEEP_ASPECT_RATIO = Qt.AspectRatioMode.KeepAspectRatio
    IMAGE_FORMAT_ARGB32 = QImage.Format.Format_ARGB32
else:
    SMOOTH_TRANSFORMATION = Qt.SmoothTransformation
    KEEP_ASPECT_RATIO = Qt.KeepAspectRatio
    IMAGE_FORMAT_ARGB32 = QImage.Format_ARGB32
DEPTH_BREAKS = (
    (-9000.0, "trench", "Below 6,000 m"),
    (-6000.0, "abyssal", "4,000–6,000 m"),
    (-4000.0, "deep", "2,000–4,000 m"),
    (-2000.0, "slope", "1,000–2,000 m"),
    (-1000.0, "upper_slope", "200–1,000 m"),
    (-200.0, "shelf", "0–200 m"),
    (0.0, "shelf", "Sea level"),
)
STATUS_DASH = {
    "treaty_delimited": "solid",
    "officially_declared": "solid",
    "provider_reference": "dash",
    "computed_reference": "dot",
    "disputed": "dash dot",
    "uncertain": "dot",
}
STATUS_WIDTH = {
    "treaty_delimited": 0.40,
    "officially_declared": 0.30,
    "provider_reference": 0.28,
    "computed_reference": 0.25,
    "disputed": 0.42,
    "uncertain": 0.38,
}


def _start_qgis() -> QgsApplication:
    application = QgsApplication([], False)
    application.initQgis()
    return application


def _color(theme: dict, dotted: str) -> str:
    value = theme["resolved_theme"]["presentation"]
    for part in dotted.split("."):
        value = value[part]
    return str(value)


def _layout_text_format(font: QFont, color: str) -> QgsTextFormat:
    text_format = QgsTextFormat()
    text_format.setFont(font)
    text_format.setSize(font.pointSizeF())
    text_format.setColor(QColor(color))
    return text_format


def _font(family: str, size: int, *, bold: bool = False) -> QFont:
    font = QFont(family, size)
    font.setBold(bold)
    return font


def _add_vector(
    project: QgsProject,
    group,
    gpkg: Path,
    layer_name: str,
    display_name: str,
) -> QgsVectorLayer | None:
    layer = QgsVectorLayer(f"{gpkg}|layername={layer_name}", display_name, "ogr")
    if not layer.isValid():
        return None
    project.addMapLayer(layer, False)
    group.insertLayer(0, layer)
    return layer


def _style_raster(layer: QgsRasterLayer, theme: dict) -> None:
    shader_function = QgsColorRampShader()
    shader_function.setColorRampType(QgsColorRampShader.Interpolated)
    shader_function.setColorRampItemList(
        [
            QgsColorRampShader.ColorRampItem(
                value, QColor(_color(theme, f"bathymetry.{key}")), label
            )
            for value, key, label in DEPTH_BREAKS
        ]
    )
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_function)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)


def _style_land(layer: QgsVectorLayer, theme: dict) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {
                    "color": _color(theme, "land.fill"),
                    "outline_color": _color(theme, "land.outline"),
                    "outline_width": "0.10",
                }
            )
        )
    )


def _style_line(layer: QgsVectorLayer, color: str, width: float, style: str = "solid") -> None:
    layer.renderer().setSymbol(
        QgsLineSymbol.createSimple(
            {"line_color": color, "line_width": str(width), "line_style": style}
        )
    )


def _style_contours(layer: QgsVectorLayer, theme: dict, profile: dict) -> None:
    categories = []
    for level in profile["contour_levels_m"]:
        major = int(level) in {-1000, -4000}
        color = _color(theme, "contours.major" if major else "contours.minor")
        width = float(profile["contour_width_mm"]) * (1.45 if major else 1.0)
        symbol = QgsLineSymbol.createSimple(
            {"line_color": color, "line_width": str(width), "line_style": "solid"}
        )
        categories.append(QgsRendererCategory(float(level), symbol, f"{abs(int(level)):,} m"))
    layer.setRenderer(QgsCategorizedSymbolRenderer("depth_m", categories))


def _style_boundaries(layer: QgsVectorLayer, theme: dict) -> None:
    categories = []
    for status, dash in STATUS_DASH.items():
        symbol = QgsLineSymbol.createSimple(
            {
                "line_color": _color(theme, f"maritime_status.{status}"),
                "line_width": str(STATUS_WIDTH[status]),
                "line_style": dash,
            }
        )
        categories.append(QgsRendererCategory(status, symbol, status.replace("_", " ").title()))
    layer.setRenderer(QgsCategorizedSymbolRenderer("legal_status", categories))


def _style_labels(layer: QgsVectorLayer, theme: dict, profile: dict) -> None:
    names = {field.name() for field in layer.fields()}
    if "NAME" in names:
        name_field = "NAME"
    elif "name" in names:
        name_field = "name"
    else:
        return
    rank_field = (
        "SCALERANK" if "SCALERANK" in names else "scalerank" if "scalerank" in names else None
    )
    settings = QgsPalLayerSettings()
    if rank_field:
        settings.fieldName = (
            f'CASE WHEN "{rank_field}" <= {int(profile["label_rank_max"])} THEN "{name_field}" END'
        )
        settings.isExpression = True
    else:
        settings.fieldName = name_field
    settings.placement = Qgis.LabelPlacement.OverPoint
    text_format = QgsTextFormat()
    text_format.setFont(QFont("Arial", round(float(profile["label_size_pt"]))))
    text_format.setSize(float(profile["label_size_pt"]))
    text_format.setColor(QColor(_color(theme, "labels.text")))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.7)
    buffer.setColor(QColor(_color(theme, "labels.halo")))
    text_format.setBuffer(buffer)
    settings.setFormat(text_format)
    settings.enabled = True
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": "0,0,0,0", "outline_color": "0,0,0,0", "size": "0"}
            )
        )
    )


def _create_contours(raster_path: Path, output_path: Path, levels: list[int]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    driver = ogr.GetDriverByName("GPKG")
    if output_path.exists():
        driver.DeleteDataSource(str(output_path))
    source = gdal.Open(str(raster_path))
    if source is None:
        raise RuntimeError(f"GDAL could not open bathymetry: {raster_path}")
    target = driver.CreateDataSource(str(output_path))
    spatial_reference = osr.SpatialReference()
    spatial_reference.ImportFromWkt(source.GetProjection())
    contour_layer = target.CreateLayer(
        "depth_contours", spatial_reference, ogr.wkbLineString, options=["SPATIAL_INDEX=NO"]
    )
    contour_layer.CreateField(ogr.FieldDefn("depth_m", ogr.OFTReal))
    band = source.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    result = gdal.ContourGenerate(
        band,
        0.0,
        0.0,
        sorted(float(level) for level in levels),
        1 if nodata is not None else 0,
        float(nodata or 0.0),
        contour_layer,
        -1,
        0,
    )
    target = None
    source = None
    if result != 0:
        raise RuntimeError(f"GDAL contour generation failed with code {result}")


def _normalize_360_raster(path: Path) -> None:
    """Convert a split-safe 0..360 display derivative to canonical longitudes for PROJ."""
    source = gdal.Open(str(path))
    if source is None:
        raise RuntimeError(f"GDAL could not open 0..360 raster: {path}")
    transform = source.GetGeoTransform()
    pixel_width = float(transform[1])
    width = round(360.0 / pixel_width)
    source_band = source.GetRasterBand(1)
    source_data = source_band.ReadAsArray()
    nodata = source_band.GetNoDataValue()
    fill_value = nodata if nodata is not None else 0
    normalized = np.full((source.RasterYSize, width), fill_value, dtype=source_data.dtype)
    centers = transform[0] + (np.arange(source.RasterXSize) + 0.5) * pixel_width
    canonical = ((centers + 180.0) % 360.0) - 180.0
    destinations = np.floor((canonical + 180.0) / pixel_width).astype(int)
    valid = (destinations >= 0) & (destinations < width)
    normalized[:, destinations[valid]] = source_data[:, valid]
    projection = source.GetProjection()
    data_type = source_band.DataType
    source = None

    temporary = path.with_name(f"{path.stem}-normalized.tif")
    target = gdal.GetDriverByName("GTiff").Create(
        str(temporary), width, normalized.shape[0], 1, data_type, options=["COMPRESS=DEFLATE"]
    )
    target.SetGeoTransform((-180.0, pixel_width, 0.0, transform[3], 0.0, transform[5]))
    target.SetProjection(projection)
    target_band = target.GetRasterBand(1)
    target_band.WriteArray(normalized)
    if nodata is not None:
        target_band.SetNoDataValue(nodata)
    target_band.FlushCache()
    target = None
    temporary.replace(path)


def _normalized_360_gpkg(source_path: Path, target_path: Path) -> None:
    """Create a canonical-longitude display copy from seam-split 0..360 vectors."""

    def shift_geometry(geometry) -> None:
        if geometry.GetGeometryCount():
            for index in range(geometry.GetGeometryCount()):
                shift_geometry(geometry.GetGeometryRef(index))
            return
        for index in range(geometry.GetPointCount()):
            x, y, _ = geometry.GetPoint(index)
            geometry.SetPoint_2D(index, x - 360.0 if x > 180.0 else x, y)

    driver = ogr.GetDriverByName("GPKG")
    if target_path.exists():
        driver.DeleteDataSource(str(target_path))
    source = ogr.Open(str(source_path))
    if source is None:
        raise RuntimeError(f"OGR could not open 0..360 GeoPackage: {source_path}")
    target = driver.CreateDataSource(str(target_path))
    for layer_index in range(source.GetLayerCount()):
        source_layer = source.GetLayerByIndex(layer_index)
        target_layer = target.CreateLayer(
            source_layer.GetName(),
            source_layer.GetSpatialRef(),
            source_layer.GetGeomType(),
            options=["SPATIAL_INDEX=NO"],
        )
        definition = source_layer.GetLayerDefn()
        for field_index in range(definition.GetFieldCount()):
            target_layer.CreateField(definition.GetFieldDefn(field_index))
        for source_feature in source_layer:
            target_feature = ogr.Feature(target_layer.GetLayerDefn())
            target_feature.SetFrom(source_feature)
            geometry = source_feature.GetGeometryRef()
            if geometry is not None:
                geometry = geometry.Clone()
                shift_geometry(geometry)
                target_feature.SetGeometry(geometry)
            target_layer.CreateFeature(target_feature)
    target = None
    source = None
    with sqlite3.connect(target_path) as connection:
        connection.execute("ATTACH DATABASE ? AS source", (str(source_path),))
        for table in ("gpkg_metadata", "gpkg_metadata_reference"):
            exists = connection.execute(
                "SELECT 1 FROM source.sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if exists:
                schema = connection.execute(
                    "SELECT sql FROM source.sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()[0]
                connection.execute(
                    schema.replace(f"CREATE TABLE {table}", f"CREATE TABLE IF NOT EXISTS {table}")
                )
                connection.execute(f"INSERT INTO {table} SELECT * FROM source.{table}")
        connection.commit()


def _extent_from_bbox(
    project: QgsProject,
    bbox: list[float],
    target_crs: QgsCoordinateReferenceSystem,
    longitude_convention: str,
) -> QgsRectangle:
    source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(source_crs, target_crs, project.transformContext())
    xmin, ymin, xmax, ymax = [float(value) for value in bbox]

    def normalize(longitude: float) -> float:
        return longitude - 360.0 if longitude_convention == "360" and longitude > 180 else longitude

    projected = []
    for index in range(181):
        fraction = index / 180.0
        x_value = xmin + (xmax - xmin) * fraction
        y_value = ymin + (ymax - ymin) * fraction
        projected.extend(
            (
                transform.transform(QgsPointXY(normalize(x_value), ymin)),
                transform.transform(QgsPointXY(normalize(x_value), ymax)),
                transform.transform(QgsPointXY(normalize(xmin), y_value)),
                transform.transform(QgsPointXY(normalize(xmax), y_value)),
            )
        )
    return QgsRectangle(
        min(point.x() for point in projected),
        min(point.y() for point in projected),
        max(point.x() for point in projected),
        max(point.y() for point in projected),
    )


def _build_layout(
    project: QgsProject,
    spec: dict,
    extent: QgsRectangle,
    crs: QgsCoordinateReferenceSystem,
    source_names: list[str],
    legend_layers: list,
) -> QgsPrintLayout:
    profile = spec["cartographic_profile"]
    layout_cfg = spec["layout"]
    theme = spec["theme"]
    build = spec["build"]
    page_width, page_height = layout_cfg["page_mm"]
    map_x, map_y, map_width, map_height = layout_cfg["map_mm"]

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(build["layout_profile"])
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(page_width, page_height, QgsUnitTypes.LayoutMillimeters))
    page.setPageStyleSymbol(
        QgsFillSymbol.createSimple(
            {"color": _color(theme, "layout.background"), "outline_style": "no"}
        )
    )
    project.layoutManager().addLayout(layout)

    title = QgsLayoutItemLabel(layout)
    title.setText(spec["region"]["purpose"])
    title.setTextFormat(
        _layout_text_format(
            _font("Arial", int(layout_cfg["title_pt"]), bold=True),
            _color(theme, "layout.title"),
        )
    )
    title.attemptMove(QgsLayoutPoint(map_x, 5, QgsUnitTypes.LayoutMillimeters))
    title.attemptResize(QgsLayoutSize(map_width, 10, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(title)

    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(map_width, map_height, QgsUnitTypes.LayoutMillimeters))
    map_item.setCrs(crs)
    map_item.zoomToExtent(extent)
    map_item.setBackgroundEnabled(True)
    map_item.setBackgroundColor(QColor(_color(theme, "bathymetry.shelf")))
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor(_color(theme, "layout.frame")))
    map_item.setFrameStrokeWidth(QgsLayoutMeasurement(0.20, QgsUnitTypes.LayoutMillimeters))
    map_item.refresh()
    layout.setReferenceMap(map_item)

    grid = QgsLayoutItemMapGrid("MGRB graticule", map_item)
    grid.setEnabled(True)
    grid.setIntervalX(float(profile["graticule_interval_degrees"]))
    grid.setIntervalY(float(profile["graticule_interval_degrees"]))
    grid.setLineSymbol(
        QgsLineSymbol.createSimple(
            {
                "line_color": _color(theme, "graticule"),
                "line_width": "0.10",
                "line_style": "dot",
            }
        )
    )
    grid.setAnnotationEnabled(bool(profile["graticule_annotation"]))
    grid.setAnnotationPrecision(0)
    map_item.grids().addGrid(grid)

    legend = QgsLayoutItemLegend(layout)
    legend.setLinkedMap(map_item)
    legend.setTitle("Public base")
    legend.setAutoUpdateModel(False)
    legend.model().rootGroup().clear()
    for layer in legend_layers:
        if layer is not None:
            legend.model().rootGroup().addLayer(layer)
    legend.setLegendFilterByMapEnabled(False)
    legend.setResizeToContents(False)
    legend.rstyle(QgsLegendStyle.Title).setTextFormat(
        QgsTextFormat.fromQFont(_font("Arial", 7, bold=True))
    )
    legend.rstyle(QgsLegendStyle.Subgroup).setTextFormat(
        QgsTextFormat.fromQFont(_font("Arial", 6, bold=True))
    )
    legend.rstyle(QgsLegendStyle.SymbolLabel).setTextFormat(
        QgsTextFormat.fromQFont(QFont("Arial", 6))
    )
    legend.setBackgroundEnabled(True)
    legend.setBackgroundColor(QColor(_color(theme, "layout.background")))
    legend.setFrameEnabled(True)
    legend.setFrameStrokeColor(QColor(_color(theme, "layout.frame")))
    legend.attemptMove(
        QgsLayoutPoint(map_x + map_width - 72, map_y + 4, QgsUnitTypes.LayoutMillimeters)
    )
    legend_height = 44 if len(profile["contour_levels_m"]) <= 3 else 62
    legend.attemptResize(QgsLayoutSize(68, legend_height, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(legend)

    if profile["scale_bar"]:
        scale_bar = QgsLayoutItemScaleBar(layout)
        scale_bar.setStyle("Single Box")
        scale_bar.setUnits(QgsUnitTypes.DistanceKilometers)
        scale_bar.setUnitLabel("km")
        scale_bar.setLinkedMap(map_item)
        scale_bar.setNumberOfSegments(3)
        scale_bar.setNumberOfSegmentsLeft(0)
        scale_bar.attemptMove(
            QgsLayoutPoint(map_x + 5, map_y + map_height - 10, QgsUnitTypes.LayoutMillimeters)
        )
        scale_bar.applyDefaultSize()
        layout.addLayoutItem(scale_bar)

    if build.get("visible_footer", True):
        footer = QgsLayoutItemLabel(layout)
        git_short = (build.get("git_commit") or "unknown")[:12]
        source_text = "; ".join(source_names)
        footer.setText(
            f"MGRB v{build['mgrb_version']} · commit {git_short} · {build['region_profile']} / "
            f"{build['cartographic_profile']} · {build['theme']['palette_id']} "
            f"{build['theme']['palette_sha256'][:12]} · Sources: {source_text} · Not for navigation"
        )
        footer.setTextFormat(
            _layout_text_format(
                QFont("Arial", round(float(layout_cfg["footer_pt"]))),
                _color(theme, "layout.footer"),
            )
        )
        footer.attemptMove(QgsLayoutPoint(map_x, page_height - 11, QgsUnitTypes.LayoutMillimeters))
        footer.attemptResize(QgsLayoutSize(map_width, 8, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(footer)
    return layout


def _project_has_private_paths(project_path: Path) -> bool:
    with zipfile.ZipFile(project_path) as archive:
        payload = b"\n".join(
            archive.read(name) for name in archive.namelist() if name.endswith((".qgs", ".xml"))
        ).decode("utf-8", errors="ignore")
    return str(ROOT).lower().replace("\\", "/") in payload.lower().replace("\\", "/")


def build_one(spec_path: Path, output_dir: Path, review_dir: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    region = spec["region"]
    build = spec["build"]
    build_id = build["build_id"]
    data_root = spec_path.parents[1]
    output_dir.mkdir(parents=True, exist_ok=True)
    qgz = output_dir / f"{build_id}.qgz"

    project = QgsProject.instance()
    project.clear()
    project.setFileName(str(qgz))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setTitle(f"MGRB | {build_id}")
    project_metadata = QgsProjectMetadata()
    project_metadata.setTitle(f"{build['formal_name']} — {build_id}")
    project_metadata.setAbstract(build["recommended_citation"])
    project_metadata.setAuthor("Maritime Geospatial Research Base (MGRB)")
    project_metadata.setKeywords(
        {
            "MGRB lineage": [
                f"version:{build['mgrb_version']}",
                f"commit:{build.get('git_commit') or 'unknown'}",
                f"build:{build_id}",
                f"theme-sha256:{build['theme']['palette_sha256']}",
                f"source-manifest-sha256:{build['source_manifest_sha256']}",
            ]
        }
    )
    project.setMetadata(project_metadata)
    crs = QgsCoordinateReferenceSystem()
    if not crs.createFromProj(region["display_crs"]):
        raise RuntimeError(f"Invalid display CRS for {region['name']}: {region['display_crs']}")
    project.setCrs(crs)
    project.setEllipsoid("WGS84")
    for key, value in {
        "mgrb_version": build["mgrb_version"],
        "mgrb_commit": build.get("git_commit") or "unknown",
        "mgrb_build_id": build_id,
        "mgrb_region": build["region_profile"],
        "mgrb_cartographic_profile": build["cartographic_profile"],
        "mgrb_layout_profile": build["layout_profile"],
        "mgrb_palette_id": build["theme"]["palette_id"],
        "mgrb_palette_origin": build["theme"]["palette_origin"],
        "mgrb_palette_sha256": build["theme"]["palette_sha256"],
        "mgrb_build_timestamp_utc": build["build_timestamp_utc"],
    }.items():
        QgsExpressionContextUtils.setProjectVariable(project, key, value)
    project.writeEntry("MGRB", "source_manifest", json.dumps(spec["sources"], sort_keys=True))
    project.writeEntry("MGRB", "style_manifest", json.dumps(spec["theme"], sort_keys=True))

    root_group = project.layerTreeRoot()
    base_group = root_group.addGroup("Public geospatial base")
    reference_group = root_group.addGroup("Maritime references — sourced/status-qualified")
    label_group = root_group.addGroup("Scale-aware labels")
    root_group.addGroup("User analytical layers (intentionally empty)")

    portable_data = output_dir / "data" / build_id
    portable_data.mkdir(parents=True, exist_ok=True)
    gpkg = portable_data / "mgrb-base.gpkg"
    bathymetry = portable_data / "gebco-bathymetry.tif"
    shutil.copy2(data_root / spec["files"]["base_gpkg"], gpkg)
    shutil.copy2(data_root / spec["files"]["bathymetry"], bathymetry)
    layer_gpkg = gpkg
    source_bathymetry = bathymetry
    if region.get("longitude_convention") == "360":
        layer_gpkg = portable_data / "mgrb-display.gpkg"
        _normalized_360_gpkg(gpkg, layer_gpkg)
        source_bathymetry = portable_data / "gebco-bathymetry-360.tif"
        shutil.move(bathymetry, source_bathymetry)
        shutil.copy2(source_bathymetry, bathymetry)
        _normalize_360_raster(bathymetry)
    bathy_layer = QgsRasterLayer(str(bathymetry), "GEBCO 2026 bathymetry")
    if not bathy_layer.isValid():
        raise RuntimeError(f"Invalid raster: {bathymetry}")
    _style_raster(bathy_layer, spec["theme"])
    project.addMapLayer(bathy_layer, False)
    base_group.addLayer(bathy_layer)

    contour_path = portable_data / "depth-contours.gpkg"
    _create_contours(
        bathymetry,
        contour_path,
        [int(level) for level in spec["cartographic_profile"]["contour_levels_m"]],
    )
    contour_layer = QgsVectorLayer(
        f"{contour_path}|layername=depth_contours", "Analytical depth contours", "ogr"
    )
    if not contour_layer.isValid():
        raise RuntimeError(f"Invalid generated contour layer: {contour_path}")
    _style_contours(contour_layer, spec["theme"], spec["cartographic_profile"])
    project.addMapLayer(contour_layer, False)
    base_group.insertLayer(0, contour_layer)

    land_layer = _add_vector(project, base_group, layer_gpkg, "land", "Land")
    if land_layer:
        _style_land(land_layer, spec["theme"])
    coastline_layer = _add_vector(project, base_group, layer_gpkg, "coastline", "Coastline")
    if coastline_layer:
        _style_line(coastline_layer, _color(spec["theme"], "coastline"), 0.24)
    boundary_layer = _add_vector(
        project, reference_group, layer_gpkg, "maritime_boundaries", "Maritime status references"
    )
    if boundary_layer:
        _style_boundaries(boundary_layer, spec["theme"])
    labels_layer = _add_vector(project, label_group, layer_gpkg, "labels", "Geographic labels")
    if labels_layer:
        _style_labels(labels_layer, spec["theme"], spec["cartographic_profile"])

    extent = _extent_from_bbox(
        project, region["bbox"], crs, region.get("longitude_convention", "180")
    )
    source_names = [
        f"{record['provider']} ({record['version_or_date']})" for record in spec["sources"]
    ]
    layout = _build_layout(
        project,
        spec,
        extent,
        crs,
        source_names,
        [contour_layer, bathy_layer, boundary_layer],
    )

    if not project.write(str(qgz)):
        raise RuntimeError(f"Failed to write QGIS project: {qgz}")
    if _project_has_private_paths(qgz):
        raise RuntimeError(f"Project serialized a private absolute path: {qgz}")

    review_dir.mkdir(parents=True, exist_ok=True)
    exporter = QgsLayoutExporter(layout)
    image_settings = QgsLayoutExporter.ImageExportSettings()
    image_settings.dpi = 300
    pdf_settings = QgsLayoutExporter.PdfExportSettings()
    pdf_settings.exportMetadata = True
    svg_settings = QgsLayoutExporter.SvgExportSettings()
    outputs = {
        "png": review_dir / f"{build_id}.png",
        "pdf": review_dir / f"{build_id}.pdf",
        "svg": review_dir / f"{build_id}.svg",
    }
    results = {
        "png": exporter.exportToImage(str(outputs["png"]), image_settings),
        "pdf": exporter.exportToPdf(str(outputs["pdf"]), pdf_settings),
        "svg": exporter.exportToSvg(str(outputs["svg"]), svg_settings),
    }
    for kind, result in results.items():
        if result != QgsLayoutExporter.Success or not outputs[kind].exists():
            raise RuntimeError(f"{kind.upper()} export failed for {build_id}: {result}")

    lineage_json = json.dumps(build, sort_keys=True)
    png_image = QImage(str(outputs["png"]))
    png_image.setText("MGRB-Lineage", lineage_json)
    png_image.setText("Description", build["recommended_citation"])
    png_metadata = outputs["png"].with_name(f"{build_id}-metadata.png")
    if not png_image.save(str(png_metadata), "PNG"):
        raise RuntimeError(f"PNG metadata embedding failed for {build_id}")
    png_metadata.replace(outputs["png"])
    svg_tree = ElementTree.parse(outputs["svg"])
    svg_metadata = ElementTree.Element("metadata", {"id": "mgrb-lineage"})
    svg_metadata.text = lineage_json
    svg_tree.getroot().insert(0, svg_metadata)
    svg_tree.write(outputs["svg"], encoding="utf-8", xml_declaration=True)

    metadata_dir = review_dir / "metadata" / build_id
    qgis_metadata_dir = output_dir / "metadata" / build_id
    metadata_dir.mkdir(parents=True, exist_ok=True)
    qgis_metadata_dir.mkdir(parents=True, exist_ok=True)
    manifest_names = {
        "build_manifest": "mgrb-build.json",
        "source_manifest": "mgrb-source-manifest.json",
        "style_manifest": "mgrb-style-manifest.json",
    }
    review_manifests = {}
    qgis_manifests = {}
    for key, name in manifest_names.items():
        relative = spec["files"].get(key)
        if relative:
            review_target = metadata_dir / name
            qgis_target = qgis_metadata_dir / name
            shutil.copy2(data_root / relative, review_target)
            shutil.copy2(data_root / relative, qgis_target)
            review_manifests[key] = review_target
            qgis_manifests[key] = qgis_target

    review_sidecars = [
        write_artifact_sidecar(
            artifact,
            review_manifests["build_manifest"],
            review_manifests["source_manifest"],
            review_manifests["style_manifest"],
        )
        for artifact in outputs.values()
    ]
    qgis_artifacts = list(
        dict.fromkeys([qgz, gpkg, layer_gpkg, source_bathymetry, bathymetry, contour_path])
    )
    qgis_sidecars = [
        write_artifact_sidecar(
            artifact,
            qgis_manifests["build_manifest"],
            qgis_manifests["source_manifest"],
            qgis_manifests["style_manifest"],
        )
        for artifact in qgis_artifacts
    ]
    write_sha256sums(
        list(outputs.values()) + review_sidecars + list(review_manifests.values()),
        metadata_dir / "SHA256SUMS",
        review_dir,
    )
    write_sha256sums(
        qgis_artifacts + qgis_sidecars + list(qgis_manifests.values()),
        qgis_metadata_dir / "SHA256SUMS",
        output_dir,
    )
    artifact_verification = {
        artifact.name: verify_generated_file(artifact)["ok"]
        for artifact in [*outputs.values(), *qgis_artifacts]
    }
    failed_verification = [name for name, ok in artifact_verification.items() if not ok]
    if failed_verification:
        raise RuntimeError(f"Generated artifact verification failed: {failed_verification}")

    reopened = QgsProject()
    if not reopened.read(str(qgz)):
        raise RuntimeError(f"QGIS could not reopen generated project: {qgz}")
    validation = {
        "build_id": build_id,
        "qgis_version": Qgis.QGIS_VERSION,
        "project": qgz.relative_to(ROOT).as_posix(),
        "layers": sorted(layer.name() for layer in reopened.mapLayers().values()),
        "layouts": sorted(item.name() for item in reopened.layoutManager().layouts()),
        "map_extent": [
            layout.referenceMap().extent().xMinimum(),
            layout.referenceMap().extent().yMinimum(),
            layout.referenceMap().extent().xMaximum(),
            layout.referenceMap().extent().yMaximum(),
        ],
        "artifact_verification": artifact_verification,
        "exports": {kind: path.relative_to(ROOT).as_posix() for kind, path in outputs.items()},
    }
    reopened.clear()
    return validation


def _journal_previews(review_dir: Path, validations: list[dict]) -> list[str]:
    preview_dir = review_dir / "journal-previews"
    preview_dir.mkdir(exist_ok=True)
    paths = []
    for validation in validations:
        source = ROOT / validation["exports"]["png"]
        image = QImage(str(source))
        for label, width in (("single-column", 1051), ("double-column", 2102)):
            target = preview_dir / f"{validation['build_id']}-{label}.png"
            image.scaledToWidth(width, SMOOTH_TRANSFORMATION).save(str(target), "PNG")
            paths.append(target.relative_to(ROOT).as_posix())
    return paths


def _contact_sheet(review_dir: Path, validations: list[dict]) -> Path:
    cell_width, cell_height, margin, title_height = 900, 620, 30, 55
    sheet = QImage(
        cell_width * 2 + margin * 3,
        cell_height * 3 + margin * 4 + title_height,
        IMAGE_FORMAT_ARGB32,
    )
    sheet.fill(QColor("#f4f4f2"))
    painter = QPainter(sheet)
    painter.setFont(_font("Arial", 24, bold=True))
    painter.setPen(QColor("#222222"))
    painter.drawText(margin, 36, "MGRB v1.0 cartography owner-review contact sheet")
    painter.setFont(QFont("Arial", 16))
    for index, validation in enumerate(validations):
        row, column = divmod(index, 2)
        x = margin + column * (cell_width + margin)
        y = margin + title_height + row * (cell_height + margin)
        image = QImage(str(ROOT / validation["exports"]["png"]))
        scaled = image.scaled(
            cell_width, cell_height - 35, KEEP_ASPECT_RATIO, SMOOTH_TRANSFORMATION
        )
        painter.drawImage(x + (cell_width - scaled.width()) // 2, y, scaled)
        painter.drawText(x, y + cell_height - 7, validation["build_id"])
    painter.end()
    target = review_dir / "contact-sheet.png"
    if not sheet.save(str(target), "PNG"):
        raise RuntimeError("Contact-sheet export failed")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--derived", type=Path, default=ROOT / "data/derived")
    parser.add_argument("--output", type=Path, default=ROOT / "qgis-projects/generated")
    parser.add_argument("--review-output", type=Path, default=ROOT / "build/owner-review")
    parser.add_argument("--build-id")
    args = parser.parse_args()
    derived_dir = args.derived.resolve()
    output_dir = args.output.resolve()
    review_dir = args.review_output.resolve()
    specs = sorted(derived_dir.glob("*/project-spec.json"))
    if args.build_id:
        specs = [path for path in specs if path.parent.name == args.build_id]
    if not specs:
        raise SystemExit("No project-spec.json files found. Prepare public regions first.")
    validations = [build_one(spec, output_dir, review_dir) for spec in specs]
    preview_paths = _journal_previews(review_dir, validations)
    contact_sheet = _contact_sheet(review_dir, validations)
    checklist = ROOT / "work/codex-v1-cartography/VISUAL_QA_CHECKLIST.md"
    shutil.copy2(checklist, review_dir / "OWNER_VISUAL_QA_CHECKLIST.md")
    summary = {
        "schema": "mgrb-owner-review-1.0",
        "status": "AUTOMATED_GATES_PASSED_PENDING_OWNER_VISUAL_REVIEW",
        "qgis_version": Qgis.QGIS_VERSION,
        "builds": validations,
        "journal_previews": preview_paths,
        "contact_sheet": contact_sheet.relative_to(ROOT).as_posix(),
        "owner_checklist": (review_dir / "OWNER_VISUAL_QA_CHECKLIST.md")
        .relative_to(ROOT)
        .as_posix(),
    }
    (review_dir / "review-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (review_dir / "qgis-validation.json").write_text(
        json.dumps(validations, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    qgis = _start_qgis()
    try:
        main()
    finally:
        qgis.exitQgis()
