# Versioned Build Spec (unreleased v1.1)

The public `mgrb-build-spec-1` contract records the MGRB version, study preset or
custom WGS84 extent, background, maritime and context layers, UTC date range,
local input paths and metadata, QC settings, and output profiles. It describes
research choices; it carries no hosted signing authority or private rendering code.

```bash
mgrb build --spec mgrb-build-spec.json --validate-spec
mgrb build --spec mgrb-build-spec.json --output-root build/outputs --output-name study
```

Use the exact MGRB version named in the document. This development contract rejects
version mismatches, unsupported QC settings, unknown fields, duplicate JSON members,
invalid dates, and files larger than 1 MiB. Validation alone does not fetch inputs or
run QGIS. A full build retains the existing public-source, QGIS and provenance checks.

Relative input paths resolve beside the JSON document. Keep the downloaded normalized
input CSV beside a spec that names it; the spec does not contain positions or upload files.
Use `input_kinds`, `input_metadata` and `field_maps` to preserve explicit local semantics.
Do not add private analytical input files or their paths to this public repository.

Version 1 pins WGS84 coordinate validation, duplicate flagging, and the existing
one-hour observed-track gap threshold. QC results and source provenance remain in
generated derivatives. Invalid data are handled by Core's normal input QC, rather
than becoming trusted merely because a spec was accepted.

Build choices come from the spec. Only `--validate-spec`, `--output-root` and
`--output-name` may accompany `--spec`; other flags are rejected instead of silently
changing or ignoring recorded choices. The legacy region-based CLI and unversioned
internal UI payloads remain supported. A hosted PNG can implement a bounded subset
of this contract; local Core remains the full PDF, SVG and QGIS package engine.

See [the machine-readable schema](../schema/product_build.schema.json) and
[public verification](official-verification.md). No release tag is changed by this
unreleased contract extension.
