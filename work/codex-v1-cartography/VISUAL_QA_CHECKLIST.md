# Owner Visual QA Checklist

This checklist is for the human owner after Codex reaches `READY_FOR_OWNER_VISUAL_REVIEW`.

Automated PASS is not sufficient for the final v1.0 release.

## Overall hierarchy

- [ ] The map is immediately understandable at normal journal figure size.
- [ ] The base is visually restrained enough for future analytical overlays.
- [ ] No component looks decorative for its own sake.
- [ ] Title, legend, scale, and source footer are secondary to the map.

## Bathymetry

- [ ] Shelf/slope/deep-ocean structure is readable.
- [ ] Important bathymetric structure is visible without overwhelming the map.
- [ ] Contours are useful and not dense.
- [ ] Hillshade/relief, if present, is subtle.
- [ ] Taiwan east/south bathymetry is especially clear in the local profile.

## Land/coastline/context

- [ ] Land tone is restrained.
- [ ] Coastline is neither too heavy nor too faint.
- [ ] The chosen public context source is appropriate for this region and scale and does not add unnecessary clutter.
- [ ] Major islands and coastlines are immediately identifiable.

## Maritime reference/status

- [ ] Different statuses remain visually distinguishable.
- [ ] Styling does not imply false legal precision or certainty.
- [ ] Line styles remain understandable in grayscale.

## Labels

- [ ] Only necessary labels are present.
- [ ] No obvious collisions.
- [ ] Typography is readable after figure reduction.
- [ ] Pacific/theatre label density is substantially lower than local/regional.

## Color/theme flexibility

- [ ] Canonical palette is restrained and useful.
- [ ] Alternate/custom palette is materially different but still coherent.
- [ ] A palette change does not alter semantic categories.
- [ ] Custom colors do not make the base compete with future analytical layers.
- [ ] Grayscale remains interpretable.
- [ ] MGRB/theme provenance remains present in metadata.

## Local profile

- [ ] Taiwan East/South local map is publication-ready.
- [ ] Extent is useful for later AIS/SAR overlays.
- [ ] Relevant bathymetric features are legible.
- [ ] There is no unnecessary regional clutter.

## Regional profile

- [ ] Regional context is clear at first glance.
- [ ] Detail is appropriately reduced relative to local.

## Pacific-wide profile

- [ ] Pacific-centered composition looks intentional.
- [ ] International Date Line handling is visually clean.
- [ ] No feature is obviously duplicated, torn, or clipped incorrectly.
- [ ] Broad physical geography is visible without local-scale noise.

## Journal-width tests

- [ ] Single-column preview remains legible.
- [ ] Double-column preview remains legible.
- [ ] Legend/source text is not too small.
- [ ] Grayscale print remains acceptable.

## Release decision

- [ ] APPROVE FOR v1.0
- [ ] RETURN FOR CARTOGRAPHIC REVISION

## Product UX and provenance

- [ ] The documented one-command build requires only region/profile/theme for routine use.
- [ ] The review package contains machine-readable build/source/style manifests and hashes.
- [ ] A representative PDF/PNG/SVG/QGZ verifies with `mgrb verify`.
- [ ] The no-visible-footer variant remains self-describing through embedded metadata and sidecars.
- [ ] Citation/provenance is informative without visually dominating the map.


## Public context source choice

- [ ] Natural Earth is used only where it is actually appropriate.
- [ ] Higher-detail or official public sources are used where they materially improve the map.
- [ ] Changing source does not break visual hierarchy.
- [ ] Source choice and version are visible in build provenance.
