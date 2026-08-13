# Required Deliverables

Codex must produce or update the MGRB repository so that the following classes of deliverables exist.

Exact paths may follow existing repository conventions, but the final report must identify them.

## 1. Cartographic configuration

Expected content:
- scale/profile definitions;
- canonical region definitions;
- projection definitions;
- theme/palette configuration;
- semantic depth/status definitions separated from color.

Example:

```text
config/
  regions/
  profiles/
  themes/
```

## 2. QGIS build implementation

Expected content:
- PyQGIS and/or `qgis_process` automation;
- deterministic project creation;
- deterministic print-layout creation;
- raster/vector preparation hooks;
- antimeridian-safe workflow.

## 3. QGIS projects/layouts

At minimum:
- local Taiwan East/South;
- regional East Asia;
- Western Pacific;
- Pacific-wide.

Reusable layout templates are preferred where technically sound.

## 4. Themes/styles

At minimum:
- canonical;
- grayscale/print-safe;
- one additional canonical theme;
- example external custom theme.

Core styles must not need direct editing for user palette customization.

## 5. Publication exports

At minimum:
- PDF;
- PNG;
- SVG where reliable.

Generate representative owner-review outputs for all required scale/theme combinations.

## 6. Provenance metadata

Emit machine-readable:
- build manifest;
- source manifest;
- resolved-theme metadata;
- theme hash;
- MGRB/commit/profile/layout/projection identifiers.

## 7. Tests/CI

Provide automated tests covering:
- configuration;
- themes;
- metadata;
- antimeridian;
- QGIS build;
- public-scope/security checks.

## 8. Documentation

Document:
- one-command or minimal-command build;
- required dependencies;
- public-source acquisition;
- scale/profile selection;
- theme customization;
- provenance/citation behavior;
- known limitations.

## 9. Owner review package

Create a stable directory such as:

```text
build/owner-review/
```

containing the six required representative renders plus a short machine-generated summary of the build parameters.


## 10. Public source registry

The implementation must expose public coastline/land/context providers through a registry or equivalent configuration mechanism. Natural Earth must be one provider option rather than a universal hard-coded dependency. Region/profile configuration should be able to select the most appropriate approved source and record that choice in provenance.

## 11. Low-input workflow and verification

Provide a one-command region/profile/theme build that performs acquisition, source
selection, derivation, QGIS project/layout/export, citation, manifests, and hashes.
Each generated artifact must be self-describing through embedded metadata where
supported plus verifiable sidecars. Provide `mgrb verify GENERATED_FILE` with an
extensible canonical-release/signature anchoring model.
