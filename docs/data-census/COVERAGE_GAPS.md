# MGRB R3 Coverage Gaps

This document states what the public-source census cannot currently support.
Blank cells in `SOURCE_COVERAGE_MATRIX.csv` mean no coverage claim; they do not
mean the actor is absent.

## Gap matrix

| Actor | Taiwan / East Asia | South China Sea | Western Pacific / Indian Ocean | Global | Principal gap |
| --- | --- | --- | --- | --- | --- |
| PLAN | Sparse official observations and daily aggregates | Incident reports/maps | Official route maps and sightings | Reports only | No lawful public dense identified historical tracks; AIS silence and operational security create selection bias. |
| CCG | Hull/event/zone evidence from Taiwan and Japan | Strong official/analytical event coverage | Sparse reports | Analytical references | No redistributable continuous 2022–2026 track archive; commercial AIS is the usual underlying source. |
| Research/Survey | Named-vessel reports; catalogs; no retrieved complete 2022–2026 local track | Cruise/station catalogs and incident evidence | Some open cruise navigation and geophysical tracklines | Voyage-dependent archives | Data are fragmented by cruise, embargo, account, institution, and file license. |
| Fishing | Excellent GFW aggregates through 2024; individual public tracks absent | Aggregates and events; identity imperfect | Good GFW aggregate coverage | Strong aggregate/identity archive | AIS excludes non-transmitting/small vessels; public archive is aggregated; 2025–2026 tested retrieval absent. |
| Maritime Militia | Sparse behavior-specific attribution | 149-row AMTI identity list and analytical maps | Little verified public coverage | None | Vessel identity does not prove militia activity at a given time; dense tracks are commercial and behavior labels are inferential. |

## Geography-specific gaps

- **Taiwan East / South / Strait / Bashi:** public official observations are
  episodic; GFW fishing aggregates are strong only through the retrieved 2024
  archive. No joined public layer supplies actor, hull/MMSI, timestamp, and dense
  coordinates for 2022–2026.
- **East China Sea / Senkaku-Diaoyu:** Japan Coast Guard statistics are strong for
  presence but not continuous position. The de-identified academic fishing data
  end in 2020 and have unresolved access/lineage.
- **South China Sea:** event/reference coverage is broad (SCSDI, ChinaPower,
  AMTI, SeaLight, SCSPI, Philippine releases), but raw redistributable tracks are
  scarce. SCSDI v1 ends in 2019.
- **Yellow Sea:** AMTI's Korean PMZ analysis relies on Starboard. Korean official
  sources confirm monitoring and AIS requirements but do not expose actor-specific
  historical tracks.
- **Western Pacific / Indian Ocean:** research-cruise repositories can yield
  voyage tracks and stations, but source-by-source retrieval and license review
  remain. Deep-sea-mining activity maps are not raw track grants.
- **Global:** GFW is strongest for fishing aggregates. PLAN/CCG global historical
  movements remain report-based or commercial.

## Detection gaps and false certainty

SAR and VIIRS can reveal vessels that AIS misses, but a detection is not an actor
identity. Matching requires time, sensor geometry, an identity candidate set,
matching thresholds, and explicit confidence. Dark-vessel detections must not be
labeled Chinese, militia, PLAN, or CCG from location alone.

Official map geometry also differs from sensor geometry. A point digitized from a
press-release map needs a `MAP_DERIVED` flag and scale-dependent uncertainty;
bearings/distances reconstructed from prose need the original reference object and
an error model. They are legitimate evidence but not GPS fixes.

## Genuinely unavailable under the public MGRB boundary

The following remain unavailable as canonical defaults:

- continuous, high-frequency, identified PLAN tracks;
- continuous, high-frequency, identified CCG tracks for 2022–2026;
- comprehensive time-bounded militia tracks with activity-state ground truth;
- raw Starboard, MarineTraffic/Kpler, Spire, ORBCOMM, HiFleet, or ShipXY history;
- partner-only Canada DVD, Skylight, and SeaVision raw products;
- a public, verified 2025–2026 Taiwan-area individual Chinese fishing track set;
- a complete open Chinese research-fleet navigation archive across institutions;
- identity-resolved SAR/VIIRS detections without independent matching evidence.

These gaps are not failures to find “the right URL.” They result from commercial
rights, operational sensitivity, transmitter behavior, data-protection policies,
partner eligibility, and the difference between observations and inferred actor
identity.

## What would change the assessment

The gap should be revisited when a provider publishes a versioned archive with a
stable DOI, machine-readable license, checksums, coordinates/timestamps, and
identity or uncertainty fields; when an account-only public-interest API grants
reproducible export; or when a user supplies a compatible commercial license.
Until then, MGRB should expose these as explicit optional connectors or references,
never silently substitute scraped map data.
