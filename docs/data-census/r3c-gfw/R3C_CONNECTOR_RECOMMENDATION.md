# R3C connector recommendation

No production connector is implemented by this audit.

## Priority

- **P0:** retain and harden checksum-pinned GFW Zenodo Fishing vessels v3 and
  monthly fleet archives. Identity and gridded presence must remain separate.
- **P1:** after the owner supplies a lawful GFW account/token, implement a
  credential-external Vessel Search identity resolver and Events client. Cache
  dataset versions, response hashes and terms evidence, never the token.
- **P1 validation spike:** manually test the documented account-gated individual
  track CSV/GeoJSON export on the reproducible 17-vessel sample. Promote only if
  repeatable, permitted, structured and automatable through a supported interface.
- **P2:** GFW interactive track view, Deep-Sea Mining Watch, SAR and VIIRS for
  reference/detection workflows.
- **P3/BYO:** licensed AIS position connectors remain user-supplied and
  non-redistributable.
- **REJECT:** UI scraping, authentication bypass, secret extraction, or relabeling
  aggregate presence/events as raw individual tracks.

The next implementation should be the authenticated GFW **identity resolver**, then
the **events client**. A raw track connector is not recommended until an official,
repeatable machine interface or a legally supported export workflow is proven.
