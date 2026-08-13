# Provenance

Every released derived product should be reproducible from a named upstream source version and a versioned MGRB workflow.

Release checklist:

- Freeze source registry versions/dates.
- Record retrieval dates and upstream hashes where available.
- Build derived products from a clean workspace.
- Generate `metadata/provenance.json` over `data/derived/`.
- Record the Git commit SHA in release notes.
- Sign the Git tag/release where the hosting environment supports it.
- Archive the release and assign a DOI when the publication workflow is ready.
