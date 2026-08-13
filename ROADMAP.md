# Roadmap to v1.0

## v0.2 — executable public-data build
- Pin Natural Earth release inputs.
- Add GSHHG ingestion.
- Add GEBCO user-defined subset workflow and TID-grid support.
- Produce a small public Taiwan-area demonstration dataset.

## v0.3 — QGIS templates
- Validate local, regional, and Pacific-wide `.qgz` projects in current QGIS LTR/current release.
- Validate `.qml` styles and print layouts.
- Add automatic version/source footer to layouts.

## v0.4 — maritime-zone provenance
- Ingest Marine Regions reference layers without mirroring provider downloads.
- Add government/treaty-source examples and status metadata.
- Validate disputed/uncertain boundary symbology.

## v0.5 — antimeridian and wide-area QA
- Validate vector splitting/wrapping at ±180° and 0/360°.
- Validate raster mosaics and Pacific-centred projections.
- Add geometry/topology regression tests.

## v0.9 — release hardening
- Clean-room rebuild from source registry.
- Reproducibility CI.
- Signed release manifest and artifact hashes.
- Citation metadata and release DOI workflow.

## v1.0 — public release
- Public-data-only QGIS-ready base.
- Reproducible builds and versioned documentation.
- DOI/citation-ready release.
