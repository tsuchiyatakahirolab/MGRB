# MGRB v1.0 Automated Acceptance Criteria

All mandatory items must pass before Codex may stop at `READY_FOR_OWNER_VISUAL_REVIEW`.

## A. Repository and reproducibility

- [ ] Work is performed in the current MGRB repository.
- [ ] Work branch is `feat/v1-cartography-system`.
- [ ] No prohibited private/analytical data are present.
- [ ] A clean documented environment can run the canonical build.
- [ ] Public upstream data provenance and licenses remain traceable.

## B. Geographic profiles

- [ ] Taiwan East/South profile builds.
- [ ] East Asia regional profile builds.
- [ ] Western Pacific profile builds.
- [ ] Pacific-wide antimeridian-safe profile builds.
- [ ] Extents and projections are documented and deterministic.

## C. QGIS execution

- [ ] Real `.qgz` projects are generated.
- [ ] QGIS/PyQGIS or `qgis_process` actually opens/processes the canonical projects.
- [ ] Canonical layouts export successfully.
- [ ] The canonical workflow does not depend on manual QGIS GUI clicking.

## D. Cartographic scale system

- [ ] Local profile has appropriate local detail.
- [ ] Regional profile reduces local clutter.
- [ ] Theatre/Pacific profile further reduces unnecessary detail.
- [ ] Labels, contours, coastline detail, and graticules respond to profile/scale.
- [ ] Base-map visual hierarchy leaves room for future analytical overlays.

## E. Bathymetry

- [ ] GEBCO treatment is reproducible.
- [ ] Depth semantics are documented separately from color.
- [ ] Useful contour/depth hierarchy is implemented.
- [ ] Relief/hillshade, if used, remains restrained.
- [ ] Bathymetry is not merely a decorative background.

## F. Public context source system

- [ ] Public context data are selected through an explicit source registry/configuration layer.
- [ ] Natural Earth is not hard-coded as the universal coastline/land/context source.
- [ ] At least two approved public-source families can be supported where relevant (for example Natural Earth and GSHHG/official data).
- [ ] Region/scale-specific source selection is documented.
- [ ] Unnecessary context is suppressed.
- [ ] Source/version/licensing metadata are retained.
- [ ] The rendered map records which source(s) supplied coastline/land/context geometry.

## G. Maritime boundaries/status

- [ ] Source/status metadata are preserved.
- [ ] Styles do not imply unsupported legal certainty.
- [ ] Relevant categories remain distinguishable without hue alone.
- [ ] Grayscale output remains interpretable.

## H. Antimeridian

- [ ] Pacific-wide raster display is continuous/correct.
- [ ] Vector geometries crossing the antimeridian are handled correctly.
- [ ] No obvious tear, false duplication, or unintended clipping occurs.
- [ ] Publication export preserves the intended Pacific-centered composition.

## I. Configurable color/theme system

- [ ] Canonical theme exists.
- [ ] Grayscale/print-safe theme exists.
- [ ] At least one additional canonical theme exists.
- [ ] External user custom theme is supported.
- [ ] Custom theme does not require editing core implementation/style files.
- [ ] Bathymetry, land, coastline, contours, reference/status layers, labels, graticule, and relevant layout colors are configurable.
- [ ] Semantic categories remain independent of hue.
- [ ] Resolved theme metadata are emitted.
- [ ] Resolved theme SHA-256 is deterministic.
- [ ] Custom theme does not remove MGRB provenance.
- [ ] Custom theme does not mutate canonical style files.
- [ ] No hidden watermark, trap data, or fabricated geography is introduced.

## J. Provenance

- [ ] Build records MGRB version.
- [ ] Build records commit SHA where available.
- [ ] Build records source manifest/version information.
- [ ] Build records region and cartographic profile.
- [ ] Build records layout profile.
- [ ] Build records CRS/projection.
- [ ] Build records palette/theme ID and origin.
- [ ] Build records deterministic palette/theme hash.
- [ ] Public outputs do not expose private absolute paths.

## K. Publication output

- [ ] Article-local PDF generated.
- [ ] Article-local PNG generated.
- [ ] Article-regional output generated.
- [ ] Article-Pacific output generated.
- [ ] Grayscale/print-safe output generated.
- [ ] SVG generated where reliable.
- [ ] Single-column-scale preview is legible.
- [ ] Double-column-scale preview is legible.

## L. Visual-review package

- [ ] Taiwan East/South local canonical render.
- [ ] Taiwan East/South local alternate/custom-theme render.
- [ ] Regional render.
- [ ] Western Pacific render.
- [ ] Pacific-wide antimeridian render.
- [ ] Grayscale render.
- [ ] Visual-review checklist copied/completed for owner review.
- [ ] Contact sheet generated if practical.

## M. Tests and CI

- [ ] Unit/config tests pass.
- [ ] Theme tests pass.
- [ ] QGIS end-to-end build test passes.
- [ ] Antimeridian test passes.
- [ ] Provenance/metadata tests pass.
- [ ] Public-tree security/scope test passes.
- [ ] CI is configured to fail on a broken canonical build.
