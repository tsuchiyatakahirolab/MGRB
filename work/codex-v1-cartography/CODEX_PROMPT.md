# Codex Task: Take MGRB to the v1.0 Cartography Release Gate

## Mission

Work only in the current **MGRB** repository.

Bring MGRB from its current state to a production-ready **v1.0 cartographic research base candidate** that can reproducibly generate publication-grade maritime base maps from public geospatial sources.

MGRB v1.0 must eliminate repeated manual background-map construction for maritime research. A researcher should be able to build a suitable local, regional, or Pacific-wide base map, then add their own analytical layers separately.

This task is about the **public geospatial base only**.

Do not add or infer:
- AIS data;
- SAR imagery or derived intelligence;
- vessel-level datasets;
- anomaly-detection logic or results;
- China-specific case material;
- intelligence or operational analysis;
- research-group internal data.

## Mandatory first steps

1. Confirm that the current working directory is the MGRB repository root.
2. Read, in full:
   - `AGENTS.md`, if present;
   - `README.md`;
   - `work/codex-v1-cartography/CARTOGRAPHY_SPEC.md`;
   - `work/codex-v1-cartography/COLOR_SYSTEM_SPEC.md`;
   - `work/codex-v1-cartography/ACCEPTANCE_CRITERIA.md`;
   - `work/codex-v1-cartography/VISUAL_QA_CHECKLIST.md`;
   - `work/codex-v1-cartography/DELIVERABLES.md`;
   - `work/codex-v1-cartography/RELEASE_GATE.md`;
   - `work/codex-v1-cartography/SECURITY_SCOPE.md`;
   - `work/codex-v1-cartography/PUBLIC_SOURCE_SELECTION_SPEC.md`.
3. Inspect the repository before editing. Reuse and improve existing implementation instead of replacing working code without reason.
4. Work on branch `feat/v1-cartography-system`. If it does not exist, create it from the current canonical branch.
5. Record the starting commit SHA in the final report.

## Core implementation requirements

### 1. Complete the reproducible public-data build

The build must support at least these canonical geographic profiles:

- `taiwan_east_south`
- `east_asia_seas`
- `west_pacific`
- `pacific_360` or an equivalently explicit antimeridian-safe Pacific profile

Use the repository's approved public-source registry. Preserve upstream provenance and licensing requirements.

The pipeline must be reproducible from a clean environment. Do not solve source or license constraints by silently vendoring data that should be obtained from the upstream provider.

### 2. Make QGIS a build engine, not a manual GUI dependency

Prefer:
- PyQGIS;
- `qgis_process`;
- GDAL/OGR;
- deterministic QGIS project/layout generation.

Manual desktop clicking must not be required for the canonical build.

If local QGIS is unavailable, use the repository's container/CI strategy or implement one using an appropriate official QGIS runtime. The final CI must actually open/build/render the QGIS outputs rather than merely lint XML.

Generate real `.qgz` projects and publication outputs.

### 3. Implement three cartographic scale profiles

Implement and document:

- **Local / event**: approximately 100–500 km research windows;
- **Regional**: Taiwan/East Asia/adjacent seas scale;
- **Theatre / Pacific**: Western Pacific and Pacific-wide views.

Scale profiles must control information density, labels, coastline/detail level, bathymetry treatment, contours, graticules, boundaries, and layout.

Do not use one universal style at every scale.

### 4. Make bathymetry analytically useful

GEBCO must not be a decorative background alone.

Provide a restrained canonical bathymetry representation and useful contour/depth hierarchy. Depth breaks, contour levels, and semantic meaning must be independent from the chosen palette.

Where hillshade or relief is used, it must remain subordinate to future analytical layers.

### 5. Implement a source-agnostic public context layer system

Do not treat Natural Earth as the mandatory or canonical source for all coastlines, land polygons, islands, labels, or political/physical context.

MGRB must support a registry of approved public geospatial sources and select or combine them according to:
- geographic area;
- cartographic scale;
- source authority;
- spatial resolution;
- update frequency;
- topology/geometry quality;
- licensing;
- analytical purpose.

Possible sources may include, where appropriate and permitted by the repository source policy:
- GEBCO;
- GSHHG;
- Natural Earth;
- official national or regional hydrographic/geospatial authorities;
- official open-data portals;
- other public, citable, well-documented geospatial datasets.

Natural Earth may remain a useful default for some small-scale/global context, but must not be hard-coded as the universal land/coastline source.

Implement source selection through the MGRB source registry/configuration layer rather than by hard-coded provider assumptions.

The base map should remain legible after a future researcher overlays analytical data.

### 6. Treat maritime boundaries as sourced analytical references

Do not represent a disputed or non-authoritative maritime boundary as an unquestioned legal fact.

Maintain source/status metadata. Where the existing MGRB schema distinguishes legal status, uncertainty, claimant/source, or reference-only use, preserve those distinctions in both data and style.

Semantics must not rely on hue alone.

### 7. Handle the antimeridian intentionally

The Pacific-wide build must correctly handle longitude convention, geometry crossing, raster/vector display, and publication layout around the International Date Line.

Do not accept a map that visually tears, duplicates features incorrectly, or clips relevant geometry because of 180-degree handling.

### 8. Implement the configurable MGRB color/theme system

Follow `COLOR_SYSTEM_SPEC.md`.

Color is configurable presentation, not MGRB identity.

Users must be able to change cartographic colors without editing core QML or Python source. Provide canonical themes plus a documented external custom-theme mechanism.

At minimum expose relevant colors for:
- bathymetry;
- land;
- coastline;
- contours;
- hillshade/relief opacity where used;
- maritime reference/status layers;
- uncertainty/dispute patterns;
- labels;
- graticule;
- layout/background.

A custom palette must not change semantic categories.

Every generated project/export must retain explicit MGRB provenance and a deterministic hash of the resolved theme. A color change must not sever MGRB lineage.

Do **not** add hidden watermarks, fake geographic features, trap data, or deceptive fingerprints.

### 9. Produce publication-grade layouts

Provide reusable layouts for at least:
- article/local;
- article/regional;
- article/Pacific;
- grayscale/print-safe variants where required.

Outputs must remain legible at common journal widths, including approximately single-column and double-column use.

Export at least:
- PDF;
- PNG;
- SVG where the QGIS stack supports reliable vector export.

Include concise source/provenance information without visually dominating the map.

### 10. Preserve and expose provenance

For each build/export, record at least:
- MGRB version;
- git commit SHA where available;
- region profile;
- cartographic scale profile;
- layout profile;
- source manifest/version information;
- CRS/projection;
- palette/theme identifier;
- canonical vs custom theme origin;
- resolved-theme SHA-256;
- whether style overrides were used;
- build timestamp.

Do not expose private local paths in public artifacts.

Emit machine-readable build/style manifests.

### 11. Automated validation

Expand tests as necessary to cover:
- public-source registry/config parsing;
- deterministic region/profile resolution;
- QGIS project creation;
- layout creation and export;
- antimeridian behavior;
- boundary/status styling;
- canonical theme resolution;
- custom-theme resolution;
- deterministic theme hashing;
- metadata/provenance embedding;
- grayscale interpretability checks that can be automated;
- absence of private or prohibited research data from the public tree.

CI should fail on a broken canonical build.

### 12. Generate owner visual-review artifacts

Create a dedicated review output directory containing representative finished renders for:

1. Taiwan East/South local, canonical theme;
2. Taiwan East/South local, alternate/custom theme;
3. regional map;
4. Western Pacific map;
5. Pacific-wide antimeridian map;
6. grayscale/print-safe map.

Also create a visual-review contact sheet if practical.

Do not use sensitive analytical overlays. Public geospatial base only.

## Design objective

The target is not simply "a map that works."

The target is a system where a researcher does not need to make repeated subjective decisions about:
- GEBCO crop/extent;
- projection;
- raster assembly;
- bathymetry hierarchy;
- coastline detail;
- label density;
- maritime reference styling;
- antimeridian handling;
- legend/layout hierarchy.

MGRB should encode strong defaults while allowing controlled presentation customization.

## Non-goals

Do not:
- build a vessel-analysis toolkit;
- add AIS/SAR adapters using licensed material;
- add intelligence data;
- create China-specific directories or examples;
- publish or tag v1.0;
- push directly to canonical `main` unless the existing repository workflow explicitly requires it and owner approval is present;
- remove upstream attribution requirements;
- invent legal certainty for maritime zones;
- hard-code one immutable color palette.

## Completion behavior

Run all automated tests and end-to-end builds.

Do not declare `v1.0.0 RELEASED`.

Stop at exactly:

`READY_FOR_OWNER_VISUAL_REVIEW`

only when:
- all mandatory automated acceptance criteria pass;
- real QGIS projects have been generated;
- required publication exports have been generated;
- visual-review artifacts are present;
- final report lists the exact commands run, PASS/FAIL results, output paths, current branch, start/end commit SHAs, and any remaining owner-only visual decisions.

If a required external dependency genuinely prevents completion, do not fake success. Implement everything possible, document the exact blocker, and state which acceptance criterion remains blocked.
