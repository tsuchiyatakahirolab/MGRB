# Citation policy

MGRB is a versioned research infrastructure. Reproducibility depends on identifying the exact release used.

## Scholarly use

When an MGRB release, template, processed layer, cartographic style, schema, workflow, or generated base map materially contributes to a publication, report, presentation, or figure, cite the exact MGRB release used. Where a persistent DOI is available, cite the DOI rather than only the GitHub URL.

A recommended methods statement is:

> Public bathymetry, coastline, maritime-zone reference layers, projection handling and cartographic standardization were prepared with the Maritime Geospatial Research Base (MGRB), version X.Y.Z.

A recommended figure note is:

> Base map: MGRB vX.Y.Z. Upstream sources are listed in the figure metadata and MGRB source manifest.

## Upstream attribution

MGRB citation does not replace citation or attribution required by GEBCO, Marine Regions, GSHHG, Natural Earth, government datasets, treaty sources, or other upstream providers. The exact sources used in a build are recorded in the source and provenance manifests.

## Modified derivatives

Users should identify material modifications to MGRB-authored templates, styles, schemas or documentation. MGRB-authored non-code materials are distributed under CC BY 4.0 and must retain the attribution required by that licence.

## Version identification

A release should be identifiable through, in descending order of preference:

1. the archived release DOI;
2. the semantic version and release tag;
3. the Git commit SHA;
4. the generated provenance manifest.

Generated publication layouts include the MGRB version in their footer by default. Removing that footer does not remove upstream or MGRB attribution obligations applicable to the materials used.
