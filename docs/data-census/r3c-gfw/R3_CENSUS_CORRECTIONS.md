# R3 census corrections: GFW individual-track access

Technical state: **PARTIAL_R3C_BLOCKED_BY_GFW_AUTHENTICATION**

## Measured result

- Crosswalk: 195 entities; 195 received a resolution attempt.
- Successfully searched against the public GFW Fishing vessels v3 archive: 153.
- Exact MMSI matches in that archive: 17; searched archive no-match: 136.
- Online-only identifiers blocked by API authentication or unsupported by the
  archive: 42.
- Ambiguous matches: 0. No name-only match was promoted.
- Actor exact-match ratios: PLAN 0/4, CCG 0/29, RESEARCH_SURVEY 0/13, FISHING 0/0, MARITIME_MILITIA 17/149, OTHER 0/0.
- Actual individual position records retrieved: **0**.

## Claims corrected

1. “GFW archive” and “GFW” are not synonymous. The tested Zenodo products contain
   annual vessel identity/activity and aggregate grid data, not positions.
2. GFW's official UI documentation separately describes individual track display
   and CSV/GeoJSON export; downloads require an account. This capability was not
   authenticated or downloaded in R3C.
3. API v3 Vessel Search provides identity/history metadata and Events provides
   algorithmic events, both with a token. No documented v3 raw individual-position
   endpoint was found.
4. Public interactive visibility, account-gated export, token-gated API, and open
   bulk archives now have separate source/interface rows and access classes.
5. Deep-Sea Mining Watch is public as an interactive aggregate portal, while its
   vessel search and event export are account-gated. Reusable individual tracks
   were not demonstrated.
6. The 17 exact GFW bulk matches were snowballed by MMSI/name against the existing
   R3 crosswalk source-link inventory. All already pointed to AMTI; no materially
   new PANGAEA, cruise, government, RFMO, SCSDI or other existing-census link was
   established, so the crosswalk source links were not inflated.

## Non-findings that remain bounded

The 178 rows without an archive identity match are not proof of no AIS
transmission. Forty-two were not searchable in the bulk archive by their strongest
identifier and remained online-authentication-blocked. The 136 exact-MMSI archive
no-matches are no-matches only in this versioned fishing-vessel archive.

## Required questions — bounded numerical answers

1. **Successfully searched:** 153/195 against the public bulk identity
   archive; all 195 received an attempt, while 42 remained online-auth-blocked.
2. **Matched GFW identity:** 17 exact MMSI matches in the tested archive.
3. **Matches by actor:** PLAN 0; CCG 0; RESEARCH_SURVEY 0; FISHING 0;
   MARITIME_MILITIA 17; OTHER 0.
4. **Matched-vessel track capability actually verified:** UI-visible 0;
   downloadable track 0; API positions 0; downloaded CSV tracks 0; downloaded
   GeoJSON tracks 0. CSV/GeoJSON export is officially documented but remained
   authentication-blocked for all 17 matches.
5. **Real position records retrieved:** 0.
6. **Taiwan/East Asia intersection, 2022–2026:** 0 confirmed. Sixteen of the 17
   matches have at least one annual archive summary in 2022–2024, but those rows
   have no coordinates, so geographic intersection was not testable.
7. **Richest public research/survey track:** no research vessel matched GFW in R3C.
   The existing R3 PANGAEA Xue Long record remains the richest verified open series
   in this census at 3,186 positions (2012), outside the R3C period.
8. **CCG usable public GFW individual tracks:** 0 demonstrated.
9. **PLAN usable public GFW individual tracks:** 0 demonstrated.
10. **Militia/fishing identities resolved:** 17/149 exact GFW bulk identities;
    0/149 yielded usable individual positions in R3C.
11. **UI capability not currently automated by the documented API:** individual
    track display and account-gated CSV/GeoJSON track export. API v3 documents
    vessel identity and events, but no raw individual-position endpoint was found.
12. **Deep-Sea Mining Watch:** aggregate map/time filtering is openly viewable;
    vessel search and event downloads are account-gated; portal-specific individual
    track export remains unverified, not proven unavailable.
13. **Original R3 claims corrected:** GFW's open bulk, interactive display,
    interactive export, identity API, events API, presence API, SAR/VIIRS, and DSMW
    capabilities now have separate access/legal/automation classifications.
14. **Connector order:** P0 bulk archive hardening; then P1 authenticated Vessel
    Search identity resolver; then P1 Events client. Do not implement a raw-track
    connector until a supported lawful machine interface is demonstrated.

## Historical snapshot / authenticated R3C-B follow-up

The numerical answers above describe the pre-authentication R3C snapshot. In the
2026-08-26 R3C-B follow-up, all 195 entities were queried through the official
authenticated API with complete pagination: 179 entities matched, including all
17 prior bulk matches and 26 of the previous 42 auth-unverified entities. Events
were retrieved for 173 entities (57,922 event records). These do not constitute
raw tracks. UI/CSV/GeoJSON validation remains manual and no raw position API
endpoint was found in the documented interface inventory. These aggregate
results were validated in the authenticated R3C audit; validation evidence is
retained privately by the project owner. Do not combine these counts with the historical bulk-only
denominators or infer that unresolved identities are non-transmitting vessels.
