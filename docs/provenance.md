# Provenance

Every released derived product should be reproducible from a named upstream source version and a versioned MGRB workflow.

Every ordinary build is also self-describing. The generated package includes build,
source, and style manifests, `SHA256SUMS`, embedded format metadata where supported,
and an artifact-specific `.mgrb.json` sidecar. Run `mgrb verify GENERATED_FILE` to
check origin, version/commit lineage, artifact integrity, and manifest consistency.
Canonical repository, DOI/persistent identifier, signed release-manifest URL/hash,
and signature URL are explicit nullable fields in `config/product.yml`; populate them
only when the owner publishes the corresponding canonical resources.

Release checklist:

- Freeze source registry versions/dates.
- Record retrieval dates and upstream hashes where available.
- Build derived products from a clean workspace.
- Generate `metadata/provenance.json` over `data/derived/`.
- Record the Git commit SHA in release notes.
- Sign the Git tag/release where the hosting environment supports it.
- Archive the release and assign a DOI when the publication workflow is ready.
