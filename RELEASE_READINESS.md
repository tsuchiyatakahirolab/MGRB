# MGRB v1.0.0 release readiness

Build date: 2026-08-12

## Passed in the build environment

- Python core tests: 8/8 PASS.
- Python bytecode compilation: PASS.
- QGIS QML style XML parsing: PASS for all included styles.
- YAML/JSON configuration and schema parsing: PASS.
- Editable package install with local build dependencies and no network/build isolation: PASS.
- Region configuration and CLI enumeration: PASS.

## Automated release gate defined but not executable in this build environment

The current build environment does not contain a real QGIS/PyQGIS runtime or Docker/Podman. The repository therefore includes GitHub Actions that run the following against official QGIS images before a public `v1.0.0` tag is treated as release-certified:

1. Headless PyQGIS project-write smoke test.
2. Synthetic GeoPackage and GeoTIFF fixture creation.
3. Automated `.qgz` generation.
4. Automated publication-layout PDF export.
5. QGIS matrix: 3.44.12 and 4.2.0.

The source implementation is v1.0.0-complete; the public release tag should be created only after this QGIS CI gate passes in GitHub.

## Publication gate

Before scholarly submission, replace the release metadata with the public GitHub repository URL and archived version DOI, then perform an independent clean-install/reuse test.
