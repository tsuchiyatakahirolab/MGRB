# Reproducible public v1.0 demo

The v1.0 release candidate uses the Xue Long 2012 Arctic cruise as its public track demo.
This is a true public position track, not event geometry or an activity aggregate.

- Provider: PANGAEA / Third Institute of Oceanography, State Oceanic Administration
- Dataset: Xue Long cruise `76XL20120717` underway observations
- DOI: <https://doi.org/10.1594/PANGAEA.891818>
- Published: 2018-07-02
- Licence: CC BY 3.0
- Input records: 3,186 published underway positions
- Source adapter: `pangaea_xue_long_2012`

Build it with:

```powershell
mgrb build xue-long-arctic-2012 `
  --background bathymetry `
  --maritime-layers eez_reference,territorial_sea `
  --output-root build/v1-release-review/public-demo `
  --output-name mgrb-v1-public-demo
```

The adapter downloads the provider table when it is not cached, records the raw SHA-256 and
DOI, normalizes the 3,186 positions, applies gap-safe segmentation, and builds the paper,
media and portable QGIS outputs through the canonical headless QGIS path. The output source
manifest retains GEBCO, Natural Earth/GSHHG, Marine Regions, and PANGAEA licences separately.

No owner-downloaded Global Fishing Watch track, private acquisition database, commercial AIS,
SAR, browser state, cookie, or token is used by this demo.
