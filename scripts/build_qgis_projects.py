#!/usr/bin/env python3
"""Build MGRB .qgz projects from public derived layers using PyQGIS.

Run inside a QGIS Python environment or the official QGIS container.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # type: ignore
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpressionContextUtils,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsPointXY,
    QgsUnitTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QFont  # type: ignore

ROOT = Path(__file__).resolve().parents[1]


def _start_qgis() -> QgsApplication:
    app = QgsApplication([], False)
    app.initQgis()
    return app


def _add_vector(project, group, gpkg: Path, layer_name: str, display_name: str, style: Path | None):
    uri = f"{gpkg}|layername={layer_name}"
    layer = QgsVectorLayer(uri, display_name, "ogr")
    if not layer.isValid():
        return None
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    if style and style.exists():
        layer.loadNamedStyle(str(style))
    return layer


def _add_raster(project, group, path: Path, display_name: str, style: Path | None):
    if not path.exists():
        return None
    layer = QgsRasterLayer(str(path), display_name)
    if not layer.isValid():
        raise RuntimeError(f"Invalid raster: {path}")
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    if style and style.exists():
        layer.loadNamedStyle(str(style))
    return layer


def _extent_from_bbox(
    project: QgsProject,
    bbox,
    target_crs: QgsCoordinateReferenceSystem,
    longitude_convention: str = "180",
) -> QgsRectangle:
    """Transform a geographic bbox to display CRS without antimeridian collapse.

    For 0..360 Pacific extents, sample the perimeter and normalize individual
    longitudes back into WGS84 before transformation. A Pacific-centred display
    CRS then keeps both sides of the antimeridian adjacent.
    """
    src = QgsCoordinateReferenceSystem("EPSG:4326")
    tx = QgsCoordinateTransform(src, target_crs, project.transformContext())
    xmin, ymin, xmax, ymax = [float(v) for v in bbox]

    if longitude_convention == "180" and target_crs == src:
        return QgsRectangle(xmin, ymin, xmax, ymax)

    def norm_lon(x: float) -> float:
        if longitude_convention == "360" and x > 180.0:
            return x - 360.0
        return x

    points = []
    steps = 180
    for i in range(steps + 1):
        t = i / steps
        x = xmin + (xmax - xmin) * t
        points.append((x, ymin))
        points.append((x, ymax))
        y = ymin + (ymax - ymin) * t
        points.append((xmin, y))
        points.append((xmax, y))

    projected = [tx.transform(QgsPointXY(norm_lon(x), y)) for x, y in points]
    xs = [p.x() for p in projected]
    ys = [p.y() for p in projected]
    return QgsRectangle(min(xs), min(ys), max(xs), max(ys))


def _build_layout(project: QgsProject, name: str, title: str, extent: QgsRectangle, crs, sources: list[str]):
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(name)
    page = layout.pageCollection().page(0)
    page.setPageSize("A4", QgsLayoutItemPage.Landscape)
    project.layoutManager().addLayout(layout)

    label = QgsLayoutItemLabel(layout)
    label.setText(title)
    label.setFont(QFont("Sans Serif", 14))
    label.attemptMove(QgsLayoutPoint(12, 7, QgsUnitTypes.LayoutMillimeters))
    label.attemptResize(QgsLayoutSize(270, 10, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(label)

    map_item = QgsLayoutItemMap(layout)
    map_item.setCrs(crs)
    map_item.zoomToExtent(extent)
    map_item.attemptMove(QgsLayoutPoint(12, 20, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(222, 165, QgsUnitTypes.LayoutMillimeters))
    map_item.setFrameEnabled(True)
    layout.addLayoutItem(map_item)

    legend = QgsLayoutItemLegend(layout)
    legend.setLinkedMap(map_item)
    legend.setTitle("Layers")
    legend.attemptMove(QgsLayoutPoint(238, 25, QgsUnitTypes.LayoutMillimeters))
    legend.attemptResize(QgsLayoutSize(48, 70, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(legend)

    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Numeric")
    scale.setLinkedMap(map_item)
    scale.attemptMove(QgsLayoutPoint(238, 103, QgsUnitTypes.LayoutMillimeters))
    scale.attemptResize(QgsLayoutSize(48, 12, QgsUnitTypes.LayoutMillimeters))
    scale.applyDefaultSize()
    layout.addLayoutItem(scale)

    footer = QgsLayoutItemLabel(layout)
    source_text = "; ".join(sources) if sources else "See project layer metadata"
    footer.setText(
        "MGRB v1.0.0 | Reproducible maritime geospatial base | "
        f"Sources: {source_text}"
    )
    footer.setFont(QFont("Sans Serif", 7))
    footer.attemptMove(QgsLayoutPoint(12, 190, QgsUnitTypes.LayoutMillimeters))
    footer.attemptResize(QgsLayoutSize(274, 8, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(footer)
    return layout


def build_one(spec_path: Path, output_dir: Path, export_preview: bool = True) -> Path:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    region = spec["region"]
    data_root = spec_path.parents[1]
    project = QgsProject.instance()
    project.clear()
    project.setTitle(f"MGRB | {region['name']}")
    project.setHomePath(str(ROOT))
    crs = QgsCoordinateReferenceSystem()
    if not crs.createFromProj(region["display_crs"]):
        raise RuntimeError(f"Invalid display CRS for {region['name']}: {region['display_crs']}")
    project.setCrs(crs)
    project.setEllipsoid("WGS84")
    QgsExpressionContextUtils.setProjectVariable(project, "mgrb_version", "1.0.0")
    QgsExpressionContextUtils.setProjectVariable(project, "mgrb_region", region["name"])

    root_group = project.layerTreeRoot()
    base_group = root_group.addGroup("Public geospatial base")
    boundary_group = root_group.addGroup("Maritime-zone references")
    root_group.addGroup("User layers")

    gpkg_rel = spec["files"].get("base_gpkg")
    gpkg = data_root / gpkg_rel if gpkg_rel else None
    bathy_rel = spec["files"].get("bathymetry")
    bathy = data_root / bathy_rel if bathy_rel else None
    loaded_sources = []

    if bathy and bathy.exists():
        if _add_raster(project, base_group, bathy, "Bathymetry", ROOT / "styles/bathymetry.qml"):
            loaded_sources.append("GEBCO_2026")
    if gpkg and gpkg.exists():
        if _add_vector(project, base_group, gpkg, "land", "Land", ROOT / "styles/land.qml"):
            loaded_sources.append("Natural Earth / configured land source")
        _add_vector(project, base_group, gpkg, "coastline", "Coastline", ROOT / "styles/coastline.qml")
        _add_vector(
            project,
            boundary_group,
            gpkg,
            "maritime_boundaries",
            "Maritime-zone references",
            ROOT / "styles/maritime_reference.qml",
        )

    bbox = region["bbox"]
    # 0..360 derivatives can be represented directly in a Pacific-centred CRS;
    # the display extent is transformed after the derivative is built.
    extent = _extent_from_bbox(
        project, bbox, crs, region.get("longitude_convention", "180")
    )
    layout = _build_layout(
        project,
        "Publication",
        f"Maritime Geospatial Research Base — {region['name'].replace('_', ' ').title()}",
        extent,
        crs,
        loaded_sources,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    qgz = output_dir / f"{region['name']}.qgz"
    if not project.write(str(qgz)):
        raise RuntimeError(f"Failed to write QGIS project: {qgz}")

    if export_preview:
        preview_dir = output_dir / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        exporter = QgsLayoutExporter(layout)
        pdf = preview_dir / f"{region['name']}.pdf"
        result = exporter.exportToPdf(str(pdf), QgsLayoutExporter.PdfExportSettings())
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Layout PDF export failed for {region['name']}: {result}")
    return qgz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", type=Path, default=ROOT / "data/derived")
    ap.add_argument("--output", type=Path, default=ROOT / "qgis-projects/generated")
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()
    specs = sorted(args.derived.glob("*/project-spec.json"))
    if not specs:
        raise SystemExit("No project-spec.json files found. Build public regions first.")
    for spec in specs:
        out = build_one(spec, args.output, export_preview=not args.no_preview)
        print(out)


if __name__ == "__main__":
    qgs = _start_qgis()
    try:
        main()
    finally:
        qgs.exitQgis()
