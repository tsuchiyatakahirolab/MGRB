# MGRB R3 China Maritime Track / Position Data Census

Status: **census complete; production ingestion intentionally not started**  
Snapshot date: 2026-08-25 (UTC evidence checks)  
Scope: public maritime geospatial infrastructure only

## Decision summary

The census found no single lawful public source that supplies dense, identified,
continuous 2022–2026 tracks for PLAN, China Coast Guard (CCG), Chinese research
vessels, fishing vessels, and maritime militia together. The practical public
architecture is therefore evidence-type-specific:

1. Global Fishing Watch (GFW) supplies reproducible Chinese-flag fishing identity
   and aggregate presence/effort through 2024, but the tested public archives do
   not supply individual point tracks.
2. PANGAEA supplies a small number of genuinely open research-cruise navigation
   series. The tested Xue Long record contains 3,186 timestamped positions.
3. Japan, Taiwan, and Philippine government releases supply legally useful but
   sparse official observations of PLAN, CCG, research, and fishing actors.
4. SCSDI and ChinaPower supply event databases, not continuous trajectories.
5. AMTI, SeaLight, SCSPI, JIIA, Deep-Sea Mining Watch, and investigations are
   excellent discovery, identity, and corroboration sources, but their mapped
   tracks often depend on commercial AIS and are not redistributable raw data.
6. MarineTraffic/Kpler, Starboard, Spire, ORBCOMM, HiFleet, and ShipXY can close
   much of the track-density gap only as optional user-supplied licensed inputs.

Accordingly, MGRB should implement a small public connector set first and retain
commercial connectors behind explicit BYO-license boundaries. A successful HTTP
response, a public map, or a paper figure is never treated as a downloadable
dataset.

## What changed from the pre-R3 MGRB inventory

The repository already knew about GFW imports, VIIRS imports, PANGAEA Xue Long,
Japan Joint Staff, Japan MOFA/JCG, Taiwan CGA, and a small vessel registry. R3
materially expanded the source universe with:

- GFW's versioned Zenodo identity and 0.1-degree monthly fleet archives, events
  API, SAR presence, and the Figshare SAR research archive;
- SCSDI's Harvard Dataverse event release and its explicit six-level location
  uncertainty model;
- ChinaPower's downloadable incident workbook;
- AMTI's downloadable 149-row Hainan maritime-militia identity sheet;
- Deep-Sea Mining Watch and the underlying GFW/Benioff methodology;
- China Polar Data Center, Digital South China Sea, NSFC shared cruises, COMS,
  Xiamen University's Jia Geng catalog, China's National Earth System Science
  Data Center, CCHDO, MGDS/R2R, and NOAA NCEI trackline archives;
- the de-identified Chinese coastal/East China Sea datasets on Kaggle, HeyWhale,
  Tianchi, and their secondary mirrors;
- NOAA/EOG VIIRS Boat Detection, Copernicus Sentinel-1, xView3, and FUSARShip;
- the partner-only Skylight, SeaVision, and Canada Dark Vessel Detection systems;
- Taiwan NODASS, China MSA accident evidence, Indonesia Bakamla observations,
  and WCPFC/IOTC/SPRFMO vessel-authorization and aggregate registries;
- the commercial AIS provider and Chinese-platform universe.

Every family is scored in `SOURCE_SCORECARD.csv`; licensing is separated into
`SOURCE_LICENSE_MATRIX.csv`. This separation matters because technical access
and legal permission are independent gates.

## Retrieval and data-quality evidence

Only records listed in `RETRIEVAL_TEST_RESULTS.csv` were actually downloaded or
tested. `DEFAULT=YES` appears only for sources with a successful R3 artifact
retrieval. The most important measurements are:

| Artifact | Result |
| --- | --- |
| GFW fishing-vessels-v3 | 773,165 rows, 22 fields, 2012–2024; 333,915 CHN vessel-year rows and 81,655 unique CHN MMSIs. Registry fields are 70–79% null. |
| GFW fleet monthly 2022, Taiwan audit bbox 117–125E/20–27N | 67,092 CHN rows; 2,922 occupied 0.1° cells; `mmsi_present` sum 1,047,800; 9,308,792.5 activity hours; 4,327,565.6 fishing hours. |
| GFW fleet monthly 2023, same bbox | 75,941 CHN rows; 3,216 cells; presence sum 1,344,036; 14,025,091.4 hours; 6,300,602.0 fishing hours. |
| GFW fleet monthly 2024, same bbox | 80,017 CHN rows; 2,976 cells; presence sum 1,353,950; 13,169,545.3 hours; 6,425,111.9 fishing hours. |
| PANGAEA Xue Long | 3,186 positions, 2012-07-17–2012-09-08, 65.0075–81.9383N and 174.03759–162.74393W; QGIS antimeridian load previously verified. |
| SCSDI Dataverse v1 | 1,241 rows, 514 unique events, 747 China-related rows, 2009–2019; location precision levels retained. |
| ChinaPower | 74 incidents, 22 fields, 2010–2020; 63 China rows; locations are text, not coordinates. |
| AMTI militia list | 149 retrieved rows, 145 primary MMSIs and 6 secondary MMSIs; analyst confidence preserved. The article's 152 count is not silently substituted. |
| GFW SAR sample | 3,172 detections/labels loaded; useful for model QA but contains no Chinese actor identity. |
| Kaggle Chinese coastal AIS | Metadata retrieved; anonymous data download returned 404. No track count is claimed. |
| NOAA/EOG VIIRS VBD | Tested data URL returned an 8,521-byte HTML login page with HTTP 200. Content validation rejected it as data. |
| China Polar Data Center | Catalog and frontend verified; attempted query endpoint returned 404. Tracks are known to exist in the catalog but were not obtained. |

The first GFW identity transfer also produced an oversized corrupt file after an
interrupted/resumed request. MD5 and parser gates rejected it; a clean download
then matched the Zenodo checksum. This is retained as a negative test result to
show why transport success alone is inadequate.

### Important metric warning

GFW `mmsi_present` in the monthly grid is a sum of vessels present per
cell/month/gear stratum. The same vessel can contribute to many cells and months.
It is **not** a count of unique vessels and must never be described that way.
Likewise, 81,655 unique CHN MMSIs is a global 2012–2024 archive result, not a
Taiwan-area or 2022–2026 track count.

## Taiwan and adjacent waters, 2022–2026

The honest result is a set of bounded measurements, not a fabricated total:

- **Identifiable PLAN vessels:** the crosswalk contains 4 currently verified
  examples from MGRB/official sources. Japan Joint Staff and Taiwan MND publicly
  report many more vessels and observations, but R3 did not complete an
  archive-wide deduplicated 2022–2026 harvest. Therefore “only four exist” would
  be false; only four are represented in the R3 crosswalk.
- **Official PLAN observations:** publicly recurring/daily products exist. No
  defensible archive total was retrieved in R3, so the count remains
  `RETRIEVED_TOTAL_NOT_ESTABLISHED` rather than zero.
- **Identifiable CCG vessels:** 29 hull numbers discovered across official and
  analytical sources are represented in the crosswalk. Public reports show more
  identities. MMSIs are generally absent and were not inferred.
- **CCG positions/tracks:** official releases contain event times, relative
  bearings/distances, maps, zone-days, and occasional routes. There is no
  retrieved public, dense, continuous CCG track series for 2022–2026. AMTI and
  SeaLight maps depend on Starboard/MarineTraffic.
- **Research vessels:** 13 named research/survey/space-tracking vessels are
  included in the crosswalk, with identifiers populated only where a cited source
  supports them. More exist in
  institutional catalogs. For Taiwan/East Asia 2022–2026, R3 retrieved no
  complete public continuous series; PANGAEA's 3,186-position Xue Long example
  is real but Arctic and from 2012.
- **Chinese fishing individual tracks:** GFW's archive identifies 34,487 CHN
  MMSIs globally in 2022, 40,933 in 2023, and 38,040 in 2024, but does not expose
  individual point tracks in the tested public archive. Kaggle/HeyWhale promise
  de-identified East China Sea tracks through 2020, outside the requested period,
  and were not fully retrieved.
- **Fishing aggregate/detection:** the 2022–2024 Taiwan-bbox GFW totals above are
  directly obtainable and reproducible. GFW's current API indicates 2025–2026
  availability after registration, but those years were not retrieved. VIIRS
  VBD is account-gated in the tested route; GFW SAR is accessible via registered
  APIs/research releases but cannot assign Chinese actor identity by detection
  alone.

Thus, for Taiwan/East Asia, the census can honestly promise hundreds of thousands
of aggregate grid rows and tens of thousands of global Chinese fishing identities,
plus sparse official actor observations. It cannot promise a public set of dense,
identified PLAN/CCG/research/militia trajectories.

## Actor-family conclusions

### PLAN

Material enrichment is possible through deterministic harvesting of Japan Joint
Staff and Taiwan MND releases. These are official observations with hull/type
identification, but often map-derived or count-only. They must be modeled as
observations with source-document, precision, observation method, and digitization
uncertainty—not self-authenticating GPS tracks.

### China Coast Guard

Japan Coast Guard longitudinal statistics and Taiwan/Philippine releases can add
zone presence, event locations, hull identities, and interactions. AMTI supplies
strong analytical context but not redistributable raw AIS. Dense identified
tracking remains a commercial-license problem.

### Research and survey vessels

This family has the best prospect for truly open tracks: PANGAEA, polar/cruise
repositories, CCHDO station records, MGDS/R2R, NCEI tracklines, and Chinese
institutional portals. Coverage is voyage-specific and license/access review is
still needed per deposit. Mining-focused identities are available through Deep-
Sea Mining Watch and the Mongabay/CNN investigation, but raw AIS remains limited.

### Fishing and maritime militia

GFW provides the largest legal gain for fishing identities and aggregates. AMTI's
149-row list materially improves militia crosswalking, while preserving
`High Confidence` versus `Likely`. It is an identity table, not proof that every
vessel was acting as militia at every time. Individual historical tracks remain
commercial, de-identified, outside the target period, or registration-gated.

## Access and evidence classes

- `OPEN_DIRECT`: a file can be downloaded without an account. It is still subject
  to license and attribution checks.
- `OPEN_REGISTRATION`: a public-interest service requires an account/token.
- `OPEN_OR_REQUEST`: metadata is public but file-level access varies.
- `OPEN_VIEWER`: visual access is not equivalent to raw export.
- `REFERENCE_ONLY`: useful publication/map, no reusable raw dataset established.
- `PARTNER_ONLY` / `CONTRIBUTOR_ONLY`: eligibility or reciprocal-data gate.
- `COMMERCIAL`: explicit contract/BYO license; no scraping or bundled data.

## Search exhaustion and blind spots

`SEARCH_LOG.csv` records 39 discovery rounds/queries across English, Simplified
Chinese, Traditional Chinese, Japanese, and Korean. Citation snowballing followed
reports back to GFW, MarineTraffic/Kpler, Starboard, government releases, cruise
archives, and supplementary tables. A late round discovered the National Earth
System Science Data Center, NODASS/China MSA/Bakamla, and RFMO registry families
and reset the stop counter each time. The final two broad rounds found only known
providers, commercial platforms within an already-scored family, official reports
without raw export, or geographically irrelevant benchmarks. That satisfies the
requested two-round stop rule without claiming omniscience.

Remaining blind spots include unindexed Chinese institutional files, changing
portal APIs, account-only catalogs, non-searchable PDF map archives, Korean and
Southeast Asian agency databases without public bulk endpoints, deleted or
version-mutated spreadsheets, and datasets whose authors cannot lawfully
redistribute the commercial AIS used in a paper.

## Reproducibility boundary

No AIS, SAR imagery, partner data, commercial data, or retrieved third-party raw
artifact is committed. The repository contains only the census, factual identity
crosswalk, retrieval measurements/hashes, URLs, and a generator. Production
connectors are recommendations only. This preserves the accepted R2 cartography
and MGRB's public-data boundary.

See also:

- `SOURCE_SCORECARD.csv` / `.json`
- `SOURCE_COVERAGE_MATRIX.csv` / `.json`
- `SOURCE_LICENSE_MATRIX.csv` / `.json`
- `SEARCH_LOG.csv` / `.json`
- `VESSEL_SOURCE_CROSSWALK.csv` / `.json`
- `RETRIEVAL_TEST_RESULTS.csv` / `.json`
- `COVERAGE_GAPS.md`
- `R3_CONNECTOR_PRIORITY.md`

## R3C GFW track-access correction

The targeted R3C audit separates GFW's interfaces. The versioned Zenodo archives
remain reproducible P0 identity/aggregate inputs, but are not individual tracks.
API v3 vessel identity and event endpoints returned HTTP 401 without an
owner-supplied Bearer token. GFW documentation describes individual track display
and account-gated CSV/GeoJSON export; R3C did not retrieve those files. Therefore
the earlier statement that the *tested public archives* lack point tracks remains
correct, but it must not be generalized to say that all GFW interfaces lack an
individual-track export. Exact counts and status distinctions are in
`r3c-gfw/R3_CENSUS_CORRECTIONS.md`.
