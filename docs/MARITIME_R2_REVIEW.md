# Maritime owner visual review R2

R2 is a targeted cartographic finish pass over the accepted maritime research
workspace. It preserves the evidence, source, vessel-registry, QGIS, provenance,
verification, and portable-package architecture.

The `taiwan-east`, `taiwan-south`, and `xue-long-arctic-2012` presets generate a
paper composition, a genuinely distinct editorial/media composition, and an
editable QGIS project. Scale bars are expressed in kilometres using rounded
intervals. Legends include only visible, available semantic classes. Geographic
orientation labels are controlled per output profile, and all headless exports
must pass bundled-font and rasterized tofu detection.

The optional World Bank Global Shipping Traffic Density source is acquired from
the provider-published archive, pinned by SHA-256, cropped without expanding the
9.8 GB GeoTIFF, averaged to a bounded regional resolution where required, and
log-transformed. Region subset caches are keyed by source hash, geographic
window, transform version, and resolution. Derived traffic texture is always an
optional contextual layer and never vessel evidence.

The rich public case uses the Xue Long cruise 76XL20120717 position dataset,
published as PANGAEA 891818 under CC BY 3.0. Its 3,186 documented positions enter
the same production normalization and quality-control path as other evidence.
They are typed `PUBLIC_TRACK`, segmented only within the resolved Xue Long
entity, and retain source citation and provider quality caveats. No AIS claim,
behavior event, loitering inference, or anomaly inference is made.

For a review root containing the three fixed build IDs, run:

```powershell
python scripts/package_maritime_r2_review.py --root build/maritime-owner-review-r2
```

This creates the six-map contact sheet, journal-width previews, portable ZIPs,
`review-summary.json`, `review-index.json`, and the review README. Validate every
QGIS package with `scripts/check_maritime_validation.py` and verify generated
artifacts with `mgrb verify` before owner review.
