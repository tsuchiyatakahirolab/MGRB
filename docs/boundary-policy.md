# Maritime-zone boundary policy

MGRB separates boundary geometry from legal meaning. A geometry is not treated as authoritative solely because it appears in a widely used global dataset.

Each maritime-zone feature should preserve the following metadata when available:

- `source_id`
- `source_date`
- `boundary_type`
- `legal_status`
- `claimant`
- `counterparty`
- `citation`
- `notes`

Recommended `legal_status` values are:

- `treaty_delimited`: supported by an applicable delimitation agreement or authoritative legal source;
- `officially_declared`: published by a competent national authority;
- `provider_reference`: third-party reference geometry;
- `computed_reference`: analytically generated comparison geometry;
- `disputed`: competing claims or unresolved delimitation are material;
- `uncertain`: provenance or status is insufficiently established.

Cartographic presentation should preserve this distinction. Provider-reference EEZ geometry should not visually imply a settled delimitation where the underlying status is disputed or unresolved.
