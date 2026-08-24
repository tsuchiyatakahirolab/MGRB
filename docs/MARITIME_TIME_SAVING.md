# Maritime workflow time-saving gate

The v1 PoC measures package preparation plus real headless-QGIS render and reopen validation.
Timing is written to `metadata/build-timing.json`. The target is at most five minutes after required
public data are available or cached.

A conservative manual workflow requires locating/reviewing sources, clipping zones and bathymetry,
choosing a projection, normalizing observations, resolving identities, checking gaps and speed,
constructing honest segments, styling confidence, organizing roughly thirty layers, creating two
layouts, exporting four files, and assembling provenance. Even with cached data and an experienced
operator, this is estimated at 60–120 minutes and dozens of dialogs/clicks.

MGRB needs one command after the researcher chooses area, period, actors, and whether local evidence
is in scope. It automates public-base reuse, Marine Regions clipping, registry resolution, evidence
normalization, QC, segmentation, layer organization, adaptive paper and 16:9 media layouts,
exports, lineage, hashes, tofu/raster/layout checks, project reopen, and portable-copy reopen.

Manual work remains where it is a research decision: source entitlement, evidentiary interpretation,
actor attribution beyond documented sources, whether inferred links are appropriate, annotations,
presentation edits, and owner visual review. Sparse official releases cannot match dense licensed
AIS temporal completeness; traffic density remains absent unless explicitly cached.
