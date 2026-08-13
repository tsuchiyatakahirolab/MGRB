# GitHub publication and v1.0.0 release

MGRB should become public before the first stable tag so that subsequent development, issues and pull requests form an open research-software history.

## Publish the repository

From the repository root, with GitHub CLI authenticated:

```bash
scripts/bootstrap_github.sh maritime-geospatial-research-base
```

The script initializes Git if needed, inserts the actual repository URL into `CITATION.cff`, commits the source, creates a public GitHub repository under the authenticated account and pushes `main`.

## Release gate

Do not create the stable tag until both `core-ci` and `qgis-ci` pass. The QGIS workflow tests headless project generation and PDF layout export against the supported QGIS matrix.

After the gate passes:

```bash
git tag -a v1.0.0 -m "MGRB v1.0.0"
git push origin v1.0.0
gh release create v1.0.0 --verify-tag --generate-notes
```

Archive the exact release with a preservation service capable of assigning a persistent identifier. Add the resulting DOI to `CITATION.cff`, README and website resource page in the next documentation commit.
