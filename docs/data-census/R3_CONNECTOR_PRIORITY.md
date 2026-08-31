# MGRB R3 Connector Priority

The smallest high-yield next step is six public connectors, sequenced below.
No connector is implemented by this census.

## Classification

- **P0:** high-value, open, clean/automatable, and legally usable after a real
  retrieval test.
- **P1:** high-value and public/public-interest, but normalization, account access,
  archive parsing, or file-level rights review remains.
- **P2:** valuable partial data, detection input, partner access, or reference.
- **P3:** user-supplied commercial/licensed connector only.
- **REJECT:** unsuitable for Chinese actor evidence or incompatible with the
  public/reproducible MGRB default.

`default_eligible=YES` is stricter than P0: R3 assigns it only where a concrete
artifact was successfully retrieved and inspected. Existing MGRB source families
are not automatically re-declared defaults merely because earlier code exists.

## Recommended implementation sequence

### P0-1: GFW versioned fishing identity and monthly fleet archives

Implement checksum-pinned downloads, schema validation, spatial subset, and a
semantic split between individual identity/activity summaries and aggregate grid
presence. Never call `mmsi_present` a unique vessel count. This produces the
largest immediate, lawful density gain for Taiwan/East Asia and global distant-
water fishing.

### P0-2: SCSDI Dataverse v1 event and uncertainty connector

Use the immutable Dataverse file/GPKGs, preserve event IDs, source reports,
precision levels, and uncertainty radii. Reject the malformed current “simple
CSV” until the provider publishes stable schema/version metadata.

### P0-3: ChinaPower incident and identity connector

Import incident facts and vessel/hull crosswalk evidence. Preserve reported place
text; do not invent coordinates. A separate reviewed geocoding enrichment may add
qualified approximate geometry later.

### P0-4: AMTI Hainan militia identity connector

Import names, primary/secondary MMSIs, and analyst confidence with an upstream
snapshot hash. The data model must distinguish vessel identity from time-specific
militia behavior. Do not reproduce commercial underlying tracks.

### P0/P1-5: official-observation harvesters

Extend deterministic Japan Joint Staff, Japan Coast Guard, Taiwan CGA/MND, and
Philippine PCG parsers. Store source URL/document hash, publication and observation
times, hull/name, observation method, textual location, derived geometry method,
and uncertainty. Run a current archive-level retrieval/license test before any new
family receives default status.

### P1-6: research-cruise broker

Build one common adapter schema for PANGAEA, China Polar Data Center, Digital South
China Sea, NORC/NSFC, National Earth System Science Data Center, CCHDO, MGDS/R2R,
and NCEI. Search by vessel aliases/IMO/MMSI, then emit either navigation tracks or
station positions without conflating them. File-level access/license results must
be cached in the source manifest.

## Secondary connectors

- **P1:** GFW registered APIs for current presence/events/SAR and NOAA VIIRS VBD
  after account/token handling. Credentials stay outside manifests; dataset
  versions and response hashes stay inside.
- **P2:** Deep-Sea Mining Watch, SeaLight, SCSPI, JIIA, Skylight, SeaVision,
  Sentinel-1/xView3/FUSARShip. These are references, model inputs, or eligibility-
  gated systems rather than public defaults.
- **P3:** MarineTraffic/Kpler, Starboard, Spire, ORBCOMM, HiFleet, ShipXY,
  ChinaPorts, VesselFinder, and FleetMon. Define an optional BYO-license interface
  with provenance fields for provider, contract-controlled product/version,
  retrieval time, allowed output operations, and non-redistribution flags. Never
  cache or ship raw licensed positions in the public repository.

## Minimum common connector contract

Each connector should return a source manifest plus one or more typed evidence
tables:

- `AIS_POSITION` / `GPS_TRACK`: vessel identifier, observation time, WGS84
  position, source-reported quality, and no inferred identity overwriting source;
- `OFFICIAL_OBSERVATION` / `MAP_DERIVED`: source document/hash, reported time,
  original location statement, derived geometry method, and uncertainty;
- `VESSEL_PRESENCE`: grid/period and aggregation semantics;
- `SAR_DETECTION` / `VIIRS_DETECTION`: sensor/product, acquisition time,
  detection confidence, and separate optional identity-match relation;
- `EVENT`: event definition/version, start/end, geometry, participants, and source;
- `STATION_POSITION` / `CRUISE_TRACK`: cruise/ship IDs and scientific repository
  provenance.

All outputs must retain canonical WGS84 separately from any Pacific-centered
derivative and must include dataset version/date, retrieval URL, access class,
license, attribution, checksum, schema version, and transformation lineage.

## Acceptance gates for future production integration

1. A successful real retrieval with content-type/magic-byte, checksum, and schema
   validation.
2. Clear legal classification for download, derived outputs, redistribution, and
   commercial use.
3. Automated count/range/timestamp/coordinate/duplicate/identity quality checks.
4. QGIS or GeoPandas load of a representative sample.
5. Explicit uncertainty and evidence-type semantics.
6. No raw licensed, partner, private, or collaborator data in the repository.
7. Provenance manifest linking every derivative to source artifact hashes.

## R3C correction to GFW priorities

- **P0 remains:** checksum-pinned GFW Zenodo fishing identity and monthly aggregate
  archives. They contain no individual positions.
- **P1 after owner authentication:** GFW API v3 vessel identity and events, plus a
  supported account-gated UI export workflow if its terms and repeatability pass.
- **P2:** interactive track display, Deep-Sea Mining Watch, SAR, and VIIRS as
  reference/detection capabilities rather than individual-track defaults.
- **REJECT for production automation now:** undocumented scraping, session/token
  extraction, or treating gridded presence as individual tracks.

No production connector is implemented by R3C.

## R3C-B authenticated evidence update (2026-08-26)

Owner-authorized Vessel Search and Events API retrieval succeeded. This removes
the authentication uncertainty for those two interfaces, not the need for a
production integration decision or license review. The audit found identity and
event geometry, with zero verified raw position records. UI-visible tracks and
CSV/GeoJSON exports remain manual-validation pending. The PANGAEA Xue Long
3,186-position public benchmark is unchanged. No production connector is
implemented or authorized by this follow-up. These aggregate findings were
validated in the authenticated R3C audit; validation evidence is retained
privately by the project owner.
