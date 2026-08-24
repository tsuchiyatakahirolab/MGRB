# Maritime source and license safety

Every adapter and build manifest records provider, product, version/date when known, download
time, original URL, license, attribution, resolution, temporal coverage, source hash, allowed use,
redistribution status, and whether commercial use is known.

Marine Regions reference zones use the provider WFS and CC BY 4.0 attribution. They are reference
features with source/status metadata, not self-authenticating legal boundaries. GEBCO is inherited
from the reproducible public base. World Bank shipping density is optional, large, and
cache-required; absence is explicit.

Japan and Taiwan official seeds contain normalized factual observations with direct official URLs
and stated precision. Original PDFs, screenshots, and page content are not redistributed.
Map-derived and text-relative locations retain uncertainty and do not become precise AIS points.

Global Fishing Watch, VIIRS, SAR, commercial AIS, and other licensed products are adapter/import
capabilities, not bundled data. Product terms must be recorded per build. Unknown commercial-use
rights emit `COMMERCIAL_USE_REQUIRES_REVIEW`.

Restricted and BYO raw files remain local and are excluded by default. The package records a local
reference and SHA-256, but does not copy protected content. No vessel/AIS/SAR/intelligence or
private research data belong in repository fixtures. The only positional test input is explicitly
named synthetic and makes no real-vessel movement claim.
