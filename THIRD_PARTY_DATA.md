# Third-party data

Apache-2.0 covers MGRB software only. MGRB does not relicense external data. Generated
packages retain a source manifest, license manifest, provenance record, and SHA-256 hashes.

| Provider | Dataset | License / terms | Attribution | Bundled in release demo | Acquisition | Redistribution |
|---|---|---|---|---|---|---|
| GEBCO Bathymetric Compilation Group | GEBCO_2026 Grid | Public-domain information product; GEBCO terms and disclaimer apply | GEBCO Compilation Group (2026), DOI 10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa | Derived subset only | Runtime provider subset/cache | Derivatives permitted with attribution and disclaimer |
| Natural Earth | Natural Earth Vector 5.1.2 | Public domain | Not required; source retained | Derived context | Pinned release | Permitted |
| Wessel & Smith / SOEST / NOAA NCEI | GSHHG 2.3.7 | GNU LGPL | Required | Derived context where selected | Pinned archive | Permitted under LGPL |
| VLIZ Marine Regions | EEZ v12, Territorial Sea v4, Contiguous Zone v4 | CC BY 4.0 | Required; geometries are reference features, not self-authenticating legal boundaries | Derived clipped layers | Official WFS | Permitted under CC BY 4.0 |
| South China Sea Data Initiative / Harvard Dataverse | News-event Data 2.0 | CC0 1.0 | Not legally required; scholarly attribution retained | Normalized geolocated event layer in flagship package | Pinned Dataverse file 6457489 | Permitted |
| PANGAEA / Third Institute of Oceanography, SOA | Xue Long cruise 76XL20120717 | CC BY 3.0 | Required; cite DOI 10.1594/PANGAEA.891818 | Normalized track in secondary demo | PANGAEA tabular endpoint | Permitted with attribution |
| World Bank / IMF | Global Shipping Traffic Density | CC BY 4.0 | Required | Not bundled unless selected and cached | Large runtime/user cache | Permitted under CC BY 4.0 |

Government-source factual observation fixtures retain source URLs and are distributed only
as normalized derived facts; source documents are not bundled. Global Fishing Watch, VIIRS,
licensed AIS/SAR, owner downloads, browser profiles, authentication/session material, and the
private bounded acquisition collector are not included in the public release.

The machine-readable canonical registry is `metadata/sources.yml`. A generated package's
`metadata/license_manifest.csv` is authoritative for the exact sources used in that build.
