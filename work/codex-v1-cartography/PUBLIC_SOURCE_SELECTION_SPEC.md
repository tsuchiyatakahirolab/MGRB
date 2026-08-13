# MGRB Public Source Selection Specification

## Principle

MGRB is source-agnostic at the platform level.

No single public map provider should be treated as the universal source for coastline, land, islands, administrative context, or labels.

## Selection criteria

For each layer and profile, select sources according to:

1. Authority and provenance.
2. Geographic suitability.
3. Resolution appropriate to the map scale.
4. Geometry/topology quality.
5. Currency/update date.
6. Licensing and redistribution conditions.
7. Reproducibility and stable citation.
8. Analytical purpose.

## Expected provider families

The registry may include, where appropriate:

- GEBCO for bathymetry;
- GSHHG for detailed global shoreline/boundary geometry;
- Natural Earth for generalized small-scale/global context;
- official national or regional hydrographic/geospatial data;
- official open-data portals;
- other public datasets approved and documented by MGRB.

This list is not exhaustive.

## Profile-aware selection

Local, regional, and theatre maps may legitimately use different sources.

For example, a local Taiwan map may use a more detailed official or high-resolution coastline source, while a Pacific-wide map may use a generalized global dataset.

## Provenance

Every build must record:
- provider;
- dataset/product name;
- version/date;
- URL or persistent identifier where applicable;
- license;
- MGRB layer(s) derived from it;
- transformation/generalization steps.

## Fallbacks

If an ideal source is unavailable or license-restricted, fall back to an approved alternative and record that fallback explicitly.

## No silent source substitution

A build must not silently switch providers without updating provenance and build metadata.
