# Maritime Geospatial Research Base (MGRB)

**A reproducible, QGIS-ready geospatial base for maritime research.**

MGRB integrates public bathymetry, coastline and maritime-zone reference data into versioned, reproducible QGIS projects for local, regional and Pacific-wide research. It standardizes acquisition, clipping, projection, antimeridian handling, cartographic styling, provenance and citation so researchers can begin with a documented geospatial base rather than rebuilding one for each project.

## What v1.0 provides

- Public-source registry with version, citation, licence and acquisition policy.
- Reproducible local, regional and Pacific-wide build profiles.
- GEBCO raster clipping and 0–360° derivatives for Pacific workflows.
- Natural Earth and GSHHG-compatible vector ingestion.
- Maritime-zone reference schema that separates geometry from legal status.
- QGIS styles for bathymetry, land, coastline and maritime-zone references.
- Headless PyQGIS project generation and publication-layout export.
- QGIS geodesic antimeridian splitting through `native:antimeridiansplit`.
- Provenance manifests with SHA-256 hashes, MGRB version and Git commit.
- CI templates for Python tests and headless QGIS validation.
- `CITATION.cff` and version-specific citation policy.

## Design principle

MGRB keeps canonical upstream geometry and data separate from generated derivatives. A derived layer is reproducible from a documented source, source version, transformation and MGRB release. Maritime-zone geometry is never assigned legal meaning solely because it appears in a global reference dataset.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
mgrb doctor
pytest -q
```

List the configured regions:

```bash
mgrb regions
```

Build a region after placing public source files in `data/raw/`:

```bash
mgrb build-region taiwan_east_south \
  --land data/raw/ne_10m_land.geojson \
  --coastline data/raw/ne_10m_coastline.geojson \
  --bathymetry data/raw/GEBCO_2026.tif
```

Then generate the QGIS project from a QGIS-enabled environment:

```bash
QT_QPA_PLATFORM=offscreen python scripts/build_qgis_projects.py
```

The project generator writes `.qgz` files and publication-layout PDF previews to `qgis-projects/generated/`.

## QGIS without manual GUI work

QGIS Desktop is not required for routine builds. QGIS provides `qgis_process` for command-line processing, while PyQGIS can create and write projects and print layouts. MGRB therefore treats QGIS as an automatable build dependency. The GUI remains useful for final visual inspection and ad hoc cartographic adjustments.

For a pinned environment, use the official QGIS container:

```bash
docker build -f docker/Dockerfile.qgis -t mgrb-qgis:1.0 .
docker run --rm -e QT_QPA_PLATFORM=offscreen \
  -v "$PWD":/workspace -w /workspace mgrb-qgis:1.0 \
  bash -lc "python scripts/qgis_smoke.py && python scripts/build_qgis_projects.py"
```

## Public data sources

The v1.0 source registry includes:

- GEBCO_2026 Grid.
- Natural Earth Vector v5.1.2.
- GSHHG v2.3.7.
- Marine Regions EEZ v12 as a third-party reference dataset.
- A schema for government, treaty, computed and disputed maritime-zone layers.

MGRB does not replace upstream attribution. Publications should cite MGRB and the upstream datasets actually used.

## Citation

Use the exact release used in a publication. GitHub recognizes `CITATION.cff`; archived releases should also receive a persistent DOI.

See `CITATION_POLICY.md`.

## Licences

- MGRB code: Apache License 2.0.
- MGRB-authored documentation, schemas and cartographic styles: CC BY 4.0.
- Upstream data retain their own terms and attribution requirements.

## Repository structure

```text
config/        region and build profiles
data/          untracked raw/derived data locations
docs/          methods and cartographic policy
metadata/      source registry and provenance metadata
mgrb/          reusable Python package
qgis-projects/ generated QGIS projects (not vendored with large data)
schema/        machine-readable metadata schemas
scripts/       public-data and PyQGIS build tools
styles/        QGIS styles
paper/         software-paper working files
tests/         automated tests
```

## Public repository

`docs/github-release.md` provides the reproducible publication sequence for a public GitHub repository, CI validation, the `v1.0.0` tag and a preserved DOI archive.

## Release standard

A v1.x release is complete only when its source registry is pinned, Python tests pass, a clean build is reproducible, QGIS smoke validation passes in a pinned QGIS environment, release files have SHA-256 hashes, and the exact version has a citable archive.
