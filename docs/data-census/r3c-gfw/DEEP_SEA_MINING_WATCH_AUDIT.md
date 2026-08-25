# Deep-Sea Mining Watch access audit

Checked: 2026-08-25

## Actual unauthenticated UI result

- The official public portal loaded its heatmap workspace, 2025-08-01–2026-08-01
  default time range, timebar controls, share-map control, and map-screenshot control.
- The Vessels section explicitly reported: **You don't have permission to search
  in these datasets.** Vessel-group details required registration/login.
- Three event-download controls explicitly required registration/login.
- No individual vessel could be selected in the unauthenticated audit; therefore
  individual history, movement-track visibility, CSV/GeoJSON track export, and an
  underlying GFW vessel ID were not demonstrated.
- No Deep-Sea-Mining-Watch-specific public API or downloadable raw track dataset
  was found. Generic GFW API v3 endpoints require a confidential Bearer token.

## Exact classification

Under the R3C DSMW decision taxonomy the interface is **REFERENCE_ONLY**. Its
access class is **OPEN_INTERACTIVE_VIEW** for aggregate activity/reference context
and time filtering. Vessel search/details and event downloads are
**ACCOUNT_REQUIRED**. Portal-specific individual-track export is
**NOT_TESTED / authentication-blocked**, not “unavailable” and not “open data.”
The displayed public map is not, by itself, evidence of reusable vessel-level
movement data.

## Reuse boundary

The portal attributes Global Fishing Watch and the Benioff Ocean Science
Laboratory/UCSB. A portal-specific raw-export redistribution grant was not found.
GFW API terms cannot be extrapolated to every embedded or third-party dataset;
dataset metadata must be reviewed after authenticated retrieval. MGRB must not
scrape the UI, extract session tokens, or represent activity heatmaps as tracks.
