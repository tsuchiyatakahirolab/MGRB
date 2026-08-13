# MGRB: A reproducible QGIS-ready geospatial base for maritime research

## Abstract

Maritime research frequently combines bathymetry, coastlines, maritime-zone reference geometries and study-specific analytical data. These components are widely available from public providers but are normally acquired, transformed, styled and documented separately for each project. This creates avoidable variation in projections, source versions, treatment of the antimeridian, representation of maritime-zone uncertainty and provenance. The Maritime Geospatial Research Base (MGRB) provides an open, versioned and reproducible workflow that converts public geospatial sources into QGIS-ready regional and Pacific-wide research bases. MGRB separates canonical source data from derived products, records source and build provenance, treats maritime-zone lines as sourced features with explicit status metadata, and supports automated QGIS project and publication-layout generation. The software is designed as a general base layer infrastructure: researchers supply their own substantive analytical data and questions.

## Implementation and architecture

MGRB is implemented in Python and uses GeoPandas/Shapely for vector transformations, Rasterio/GDAL-compatible rasters for bathymetric derivatives, PyProj for coordinate handling and PyQGIS for project and layout generation. Geographic source material is kept separate from generated derivatives. Region definitions specify an analysis extent, longitude convention and display coordinate reference system. Local and regional products use conventional -180 to +180 longitude. Pacific-wide products support a continuous 0 to 360 derivative while retaining WGS84 canonical inputs.

The project includes a boundary-status schema that records source, source date, boundary type, legal or provider status, claimant information, method and citation. This allows an analytical reference boundary, an officially declared line, a treaty-delimited boundary and a disputed or uncertain feature to remain distinguishable in both the data model and cartography. MGRB does not substitute one generalized boundary dataset for the legal and evidentiary status of the underlying source.

PyQGIS scripts generate QGIS projects, layer groups, styles and publication layouts without requiring manual desktop interaction. QGIS Processing is used where native geodesic operations are preferable, including antimeridian splitting. Headless tests are designed to run against supported QGIS releases in containerized continuous integration.

## Quality control

MGRB includes unit tests for longitude conversion, antimeridian-spanning raster extraction, regional build generation, schema validity and file-level provenance. Each derived release can be accompanied by a SHA-256 manifest, MGRB version, source metadata and Git commit identifier. Continuous integration tests the Python core and separately exercises PyQGIS project creation and PDF layout export using synthetic fixtures that are not distributed as research geography.

## Availability and reuse potential

MGRB is intended for research in which users need a documented maritime geographic base before adding their own analytical datasets. Potential applications include ocean governance, maritime law, fisheries, environmental studies, maritime security, shipping, ocean history and other spatial research. The public repository contains only reproducible public geospatial infrastructure. Provider-controlled datasets are acquired under their own terms, and upstream citations remain required alongside citation of the MGRB release used to generate derivatives.

The software code is released under the Apache License 2.0. MGRB-authored documentation, schemas and cartographic styles are released under Creative Commons Attribution 4.0, subject to the rights and terms of upstream data providers. Versioned releases are intended to be archived with a persistent identifier so that methods and figures can identify the exact MGRB version used.

## Limitations

MGRB standardizes acquisition, transformation, metadata and cartography but does not establish the legal validity of maritime claims or delimitations. Accuracy remains bounded by the source datasets selected by the user. High-resolution regional work may require official or specialist datasets beyond the global sources listed in the default registry. Projection and antimeridian choices remain scale-dependent and should be evaluated against the purpose of each map.

## Acknowledgements

Technical review and contributor acknowledgements will be added only for individuals who make identifiable contributions to the released software or documentation.
