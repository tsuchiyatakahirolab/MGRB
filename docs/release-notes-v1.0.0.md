# MGRB v1.0.0 — First Public Release

MGRB turns public maritime data and local research inputs into publication-ready maps and
portable, reproducible QGIS research workspaces. Researchers make research choices; MGRB
handles routine GIS engineering and records the resulting lineage.

## Highlights

- Loopback-only local browser UI with area, layer, background, input, QC, and output choices.
- Taiwan, East Asia, South China Sea, Western Pacific, Pacific-wide, and custom extents.
- Clean publication, bathymetry, bathymetry/relief, grayscale, navigation/context,
  provider-configured imagery reference, and no-background modes.
- Territorial sea, contiguous zone, EEZ/reference EEZ, sourced maritime boundary,
  continental-shelf, custom, and computed equidistance reference layers.
- CSV, TSV, GeoJSON/JSON, GeoPackage, and Shapefile ingest with automatic schema detection
  and explicit confirmation when fields are ambiguous.
- Position/time QC, provider segment preservation, duplicate/gap reporting, and gap-safe
  observed-track segmentation. Event geometry is never promoted to raw vessel positions.
- Adaptive paper PDF/PNG/SVG, 85 mm journal preview, and distinct media PNG.
- Relative-path QGIS project with organized GeoPackages and documented layer semantics.
- Build/source/style/license/provenance manifests, embedded metadata, sidecars,
  `SHA256SUMS`, and `mgrb verify`.
- Headless font/tofu, raster-footprint, adaptive-layout, and portable-reopen gates validated
  with QGIS 3.44 LTR and QGIS 4.2.

## Public demonstrations

The flagship is a South China Sea evidence workspace built from 1,200 geolocated records
within the selected extent from **South China Sea Data Initiative: News-event Data 2.0**
([doi:10.7910/DVN/GCBWA6](https://doi.org/10.7910/DVN/GCBWA6), CC0 1.0), GEBCO 2026,
and Marine Regions reference zones. Provider location precision and uncertainty are retained;
the event points are not represented as vessel tracks.

The secondary reproducibility/track-ingestion demo uses 3,186 published underway positions
from the Xue Long cruise `76XL20120717` in PANGAEA
([doi:10.1594/PANGAEA.891818](https://doi.org/10.1594/PANGAEA.891818), CC BY 3.0).

## Scope and boundaries

MGRB automates research-workspace preparation; it does not replace QGIS or upstream data
providers. Maritime-zone geometry is sourced or computed reference material, not
self-authenticating legal boundaries. External datasets retain their own licenses.

Private/licensed AIS or SAR, owner GFW downloads, authentication/session material, and the
private bounded acquisition collector are **not included** in this public release.

## Validation

The release commit passed the complete Python test suite, compileall, Ruff, clean-clone
installation, local UI/upload/preview tests, QGIS 3.44 and 4.2 export/reopen validation,
artifact verification, and working-tree/tracked/history/release-asset security scans.
