# Maritime Geospatial Research Base (MGRB)

**A reproducible, QGIS-ready geospatial base for maritime research.**

MGRB v1 also provides one-command maritime evidence workspaces for the `taiwan-east` and
`taiwan-south` presets. See the [maritime workspace guide](docs/MARITIME_RESEARCH_WORKSPACE.md)
for evidence semantics, portable QGIS packaging, and CLI use.

MGRB integrates public bathymetry, coastline and maritime-zone reference data into versioned, reproducible QGIS projects for local, regional and Pacific-wide research. It standardizes acquisition, clipping, projection, antimeridian handling, cartographic styling, provenance and citation so researchers can begin with a documented geospatial base rather than rebuilding one for each project.

The v1.0 product workflow is deliberately small: select an area, background and maritime
layers; optionally drop position data; preview; then build publication, media and portable
QGIS research outputs. MGRB asks for research choices and takes responsibility for routine
CRS, source, resolution, clipping, antimeridian, label, layout and attribution decisions.

## What v1.0 provides

- Public-source registry with version, citation, licence and acquisition policy.
- Reproducible local, regional and Pacific-wide build profiles.
- GEBCO raster clipping and 0–360° derivatives for Pacific workflows.
- Natural Earth and GSHHG-compatible vector ingestion.
- Maritime-zone reference schema that separates geometry from legal status.
- QGIS styles for bathymetry, land, coastline and maritime-zone references.
- Headless PyQGIS project generation and publication-layout export.
- Release-bundled OFL typography with headless glyph/tofu render validation.
- Buffered source acquisition and adaptive portrait/square/landscape page geometry.
- QGIS geodesic antimeridian splitting through `native:antimeridiansplit`.
- Provenance manifests with SHA-256 hashes, MGRB version and Git commit.
- CI templates for Python tests and headless QGIS validation.
- `CITATION.cff` and version-specific citation policy.
- A loopback-only local UI with drag/drop, schema confirmation and compact evidence QC.
- Portable QGIS research packages with paper, media and journal-width outputs.

## Design principle

MGRB keeps canonical upstream geometry and data separate from generated derivatives. A derived layer is reproducible from a documented source, source version, transformation and MGRB release. Maritime-zone geometry is never assigned legal meaning solely because it appears in a global reference dataset.

## Quick start: local product UI

```bash
python -m venv .venv
source .venv/bin/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
mgrb doctor
pytest -q
mgrb ui
```

The browser interface runs locally on `127.0.0.1`. Choose a research area, background and
maritime reference layers, drop or select a CSV/GeoJSON/GeoPackage, inspect the schema/QC,
and select **Build Research Package**. User inputs remain local and generated products are
written under `build/products/` by default. See [the product UI guide](docs/product-ui.md).

Supported presets include Taiwan East, Taiwan South, Taiwan Strait, Bashi/Luzon Strait,
East China Sea, South China Sea, Western Pacific, Pacific-wide, and the public Xue Long demo.
Custom WGS84 bounding boxes receive an adaptive CRS, scale profile and page orientation.

## CLI quick start

List the configured regions:

```bash
mgrb regions
```

Build a region after placing public source files in `data/raw/`. The profile is
canonical for the region, while a built-in theme ID or external YAML file can be
selected without editing Python or QML:

```bash
mgrb build taiwan_east_south --profile local --theme canonical
```

For a complete maritime research package with local user positions:

```bash
mgrb build taiwan-east --background bathymetry \
  --maritime-layers eez_reference,territorial_sea \
  --input vessel.csv --output-name taiwan-study
```

Then generate the QGIS project from a QGIS-enabled environment:

```bash
QT_QPA_PLATFORM=offscreen python scripts/build_qgis_projects.py
```

The project generator writes real `.qgz` files to `qgis-projects/generated/` and
PDF, PNG, SVG, journal-width previews, manifests, and a contact sheet to
`build/owner-review/`.

The reproducible v1.0 public demo uses 3,186 Xue Long positions published by PANGAEA under
CC BY 3.0. Its exact command, DOI, and licence are documented in
[the public demo guide](docs/public-demo.md).

## Canonical cartography gate build

The owner-review build acquires pinned Natural Earth and GSHHG archives and numeric
GEBCO 2026 subsets from the official CEDA/THREDDS service. Raw and derived data remain
untracked. Run it in a QGIS-enabled environment:

```bash
python scripts/prepare_owner_review.py
QT_QPA_PLATFORM=offscreen python scripts/build_qgis_projects.py
```

This produces the six required review variants: local canonical, local external
custom theme, overlay-quiet regional, Western Pacific, Pacific-wide 0–360, and
grayscale. Each export is blocked if the actual PNG contains repeated missing-glyph
boxes, if source coverage cannot fill the projectable map-frame edge, or if layout
orientation/margins are unsuitable. See
`docs/cartography-system.md` for profile, theme, source-selection, antimeridian,
provenance, and citation details.

The one-command product workflow asks for research choices only. It acquires pinned
public inputs, selects GSHHG or Natural Earth by region/scale, requests an official
GEBCO subset, applies projection and antimeridian defaults, generates derived
GeoPackages/contours, invokes headless QGIS, and packages QGZ/PDF/PNG/SVG plus
citation/provenance artifacts. Advanced source-file arguments remain available for
specialist controlled-input builds.

Every generated file has a `.mgrb.json` lineage sidecar. Verify origin and detect
post-build modification with:

```bash
mgrb verify build/outputs/BUILD_ID/BUILD_ID.pdf
```

Use `--no-visible-footer` when a journal requires an unmarked figure. QGZ/project
metadata, GeoPackage metadata, PNG/SVG metadata, PDF project metadata, sidecar
manifests, and hashes remain present. Configure the canonical repository, release DOI,
and future signed release-manifest anchors in `config/product.yml` before publication;
v1.0 does not claim an unpublished signature or DOI.

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
