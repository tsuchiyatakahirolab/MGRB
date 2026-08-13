# MGRB agent instructions

## Scope
MGRB is a public, reproducible, QGIS-ready geospatial base for maritime research.
Only public geospatial infrastructure belongs in this repository.

## Hard boundary
Do not add, infer, synthesize, reference, or create directories for licensed or non-public analytical data. In particular, do not commit vessel data, AIS, SAR, intelligence products, unpublished case material, anomaly outputs, private research notes, or collaborator-provided data.

## Required checks
Before proposing a merge or release:
1. `python -m pytest -q`
2. `python -m compileall -q mgrb scripts tests`
3. `ruff check mgrb scripts tests` when Ruff is available
4. QGIS CI must pass on the supported QGIS matrix.
5. Verify generated artifacts contain MGRB version/provenance and upstream source attribution where applicable.

## Design rules
- Preserve canonical source files; generate derivatives into `data/derived/`.
- Treat maritime-zone lines as sourced reference features with status metadata, not as self-authenticating legal boundaries.
- Keep canonical WGS84 source geometry separate from Pacific-centred 0..360 derivatives.
- Use provider-pinned versions where possible.
- Do not silently replace or rewrite source attribution or upstream licensing.
- Prefer deterministic build scripts over manual QGIS GUI operations.

## Release rule
A tagged release must be reproducible from public inputs and must not depend on any private dataset.
