# MGRB 1.0.0 release notes — draft

MGRB 1.0.0 turns the accepted reproducible cartography and maritime-evidence engine into a
local research-workspace product. A researcher selects an area, conceptual background,
maritime reference layers, and optional local position data; MGRB resolves GIS defaults and
produces publication, media, and editable portable QGIS outputs.

## Highlights

- `mgrb ui`: local, loopback-only browser interface with drag/drop and file selection.
- Presets for Taiwan and East Asian research areas plus Western Pacific and Pacific contexts.
- CSV/TSV, GeoJSON, GeoPackage, and Shapefile schema detection and confirmation.
- Evidence-safe QC and track segmentation that preserves gaps and provider segment IDs.
- Independent maritime-layer state with legal/cartographic status distinctions.
- Advanced computed median/equidistance references labelled `COMPUTED_REFERENCE`.
- Clean publication, bathymetry, relief, grayscale, context, optional imagery, and no-background
  choices mapped to the canonical theme system.
- Paper PDF/SVG/PNG, differentiated media PNG, 85 mm journal preview, relative-path QGZ,
  organized GeoPackages, metadata, provenance, source/style manifests, and SHA-256 checks.
- Public CC BY 3.0 Xue Long/PANGAEA true-track demo with 3,186 positions.
- QGIS 3.44 LTR and 4.2 CI definitions, tofu/raster/layout QA, portable reopen, and verification.

## Boundaries

MGRB automates QGIS setup; it does not replace QGIS. Maritime-zone lines are sourced or
computed reference features, not self-authenticating legal boundaries. External datasets keep
their original licences. User-supplied files are processed locally and are not public release
assets.

The private bounded GFW acquisition system, its session state, owner-downloaded tracks, and
private database are not part of this release.

## Release status

This document is a release-candidate draft. No `v1.0.0` tag, GitHub Release, DOI, or signed
release manifest exists until owner approval and the supported QGIS CI matrix pass on the
published commit.
