# QGIS automation

MGRB uses QGIS as an automatable geospatial engine rather than requiring repetitive desktop interaction.

## Supported paths

1. **PyQGIS:** `scripts/build_qgis_projects.py` creates `.qgz` projects, layer groups and publication layouts.
2. **qgis_process:** QGIS Processing algorithms can be run without starting QGIS Desktop. MGRB uses this path for QGIS-native geometry operations such as geodesic antimeridian splitting.
3. **Official QGIS container:** `docker/Dockerfile.qgis` pins a QGIS runtime so automated agents and CI can execute the same build.
4. **QGIS Desktop:** final visual inspection, exploratory layer changes and manual cartographic review.

## Agent workflow

Coding agents can edit the repository and execute PyQGIS, GDAL-compatible Python and `qgis_process` commands as long as the relevant QGIS runtime is installed or available through Docker. The preferred workflow is therefore command-driven. GUI automation is not required for the reproducible build.

## Final human review

Automated tests verify files, layers, projections, project serialization and output generation. A release should also receive one visual review in QGIS Desktop for label placement, clipping, legend readability and projection appearance at each supported scale.
