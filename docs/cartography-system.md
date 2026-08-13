# v1.0 cartography system

MGRB encodes geographic, scale, semantic, source, and presentation decisions in
separate versioned configuration layers. QGIS is the deterministic build and export
engine; the canonical workflow requires no desktop clicking.

## Canonical regions and projections

`config/regions.yml` defines deterministic extents and display projections.

| Region | Extent | Longitude | Display projection | Profile |
|---|---|---|---|---|
| `taiwan_east_south` | 119–124.5°E, 18.5–25.5°N | −180..180 | Taiwan-centred LAEA | local |
| `east_asia_seas` | 115–145°E, 15–45°N | −180..180 | East Asia-centred LAEA | regional |
| `west_pacific` | 100–179.999°E, 10°S–55°N | −180..180 | Robinson, 150°E central meridian | theatre |
| `pacific_360` | 100–300°E, 60°S–70°N | 0..360 | Robinson, 180° central meridian | theatre |

Canonical provider geometry remains untouched. The `pacific_360` build creates
separate vector/raster derivatives; the raster is assembled from two official GEBCO
subsets and the western-hemisphere part is shifted by +360°. Project generation
samples the Pacific perimeter before projection so the intended map extent cannot
collapse at ±180°.

## Scale profiles

`config/profiles.yml` controls contour levels and weights, coastline source/detail,
label rank and size, graticule spacing, scale-bar use, and layout. Local and regional
profiles retain five analytically meaningful GEBCO contours. Theatre maps use only
the 1,000 m, 4,000 m, and 6,000 m depth references, sparser labels, a 15° graticule,
and no misleading Pacific-wide linear scale bar.

Depth meanings and maritime-status meanings are defined in
`config/semantics.yml`, not in a palette. Status lines use dash pattern and width in
addition to color, so disputed, uncertain, provider-reference, and authoritative
source categories remain distinguishable in grayscale.

## Source selection

`metadata/sources.yml` is the approved registry. Each region lists ordered source
preferences by layer. Local and regional builds prefer GSHHG shoreline geometry;
theatre/Pacific builds prefer generalized Natural Earth geometry. Natural Earth is
therefore one provider option rather than a universal context dependency. GEBCO
2026 is the canonical numeric bathymetry source.

Every build manifest records provider, product, version/date, URL or DOI, licence,
layers supplied, and transformations. An unavailable preferred source must be
explicitly overridden and the chosen source recorded; silent substitution is not
supported.

## Theme resolution

Canonical themes live in `config/themes/`: `canonical`, `grayscale`, and
`print-muted`. An external theme is a partial YAML override of canonical presentation
values; `examples/custom-theme.yml` is a complete example.

```bash
mgrb build taiwan_east_south --profile local --theme canonical \
  --land data/raw/GSHHS_h_L1.shp --bathymetry data/raw/taiwan-gebco.tif

mgrb build taiwan_east_south --profile local --theme /path/to/theme.yml \
  --land data/raw/GSHHS_h_L1.shp --bathymetry data/raw/taiwan-gebco.tif
```

Resolution validates all colors and opacities, rejects unknown keys, inherits
omitted values, and calculates SHA-256 over canonical JSON serialization. The
resolved theme, origin, hash, and override flag are written to build metadata and
QGIS project variables. A custom palette changes presentation only; depth/status
semantics, geometry, attribution, and MGRB lineage remain unchanged.

## Publication layouts and provenance

The layouts are article-local (210×148 mm), article-regional (240×170 mm), and
article-Pacific (280×170 mm). QGIS exports each representative build as PDF, 300 dpi
PNG, and SVG, then reopens every `.qgz` and records its QGIS version, layers, layouts,
and export paths. Single-column (89 mm) and double-column (178 mm) previews are
generated from the QGIS render.

Each project/export records MGRB version, Git commit, build timestamp, region,
cartographic and layout profiles, CRS, longitude convention, source manifest, theme
ID/origin/hash, and override state. Paths in public manifests and serialized projects
are repository-relative; private local paths are rejected.

## Reproduce the owner-review package

Use the pinned official QGIS container or an equivalent QGIS 3.44 environment:

```bash
docker build --build-arg QGIS_IMAGE=qgis/qgis:3.44.12 \
  -f docker/Dockerfile.qgis -t mgrb-qgis:3.44 .
docker run --rm -e QT_QPA_PLATFORM=offscreen \
  -v "$PWD:/workspace" -w /workspace mgrb-qgis:3.44 \
  bash -lc "python3 scripts/prepare_owner_review.py && python3 scripts/build_qgis_projects.py"
```

Upstream archives, GEBCO subsets, derived GeoPackages/GeoTIFFs, generated QGIS
projects, and review exports are intentionally ignored by Git. The acquisition and
build manifests retain their public-source hashes and citations.

## Low-input product workflow and verification

`mgrb.workflow.execute_build(BuildRequest(...))` is the high-level service used by
the CLI. It deliberately accepts region, profile, theme, destination, optional build
ID, and visible-footer policy—not CRS, grid stride, contour levels, source resolution,
or label density. A future QGIS Processing provider or GUI can call this same service
after presenting three selectors and a Run action.

Each package contains `mgrb-build.json`, `mgrb-source-manifest.json`,
`mgrb-style-manifest.json`, per-artifact `.mgrb.json` lineage sidecars, and
`SHA256SUMS`. The build record includes the formal product name, version, configurable
canonical repository and persistent identifier, Git commit, build ID, region/profile,
layout, theme origin/hash, source manifest ID/hash, public source records, CRS,
timestamp, visible-footer policy, recommended citation, and reserved canonical
release-manifest/signature anchors.

QGZ stores project metadata, MGRB variables, source/style records, and relative data
paths. GeoPackages use `gpkg_metadata`; PNG and SVG carry embedded lineage text; PDF
inherits QGIS project title/abstract/keywords. Sidecars remain authoritative where a
format cannot carry the full record. `mgrb verify FILE` checks the artifact hash,
manifest hashes, build-to-source ID/hash, build-to-style theme hash, and reports
whether canonical repository/release anchors have been configured. It never treats an
absent future signature as present.
