# MGRB maritime research workspace v1

MGRB accelerates repeatable GIS preparation around maritime research. It does not replace QGIS
and it does not claim that AIS is complete evidence. The researcher selects an area, period,
actors, and optional local inputs; MGRB resolves preset GIS engineering, prepares the public base,
normalizes defensible observations, runs quality control, organizes an editable QGIS project, and
exports paper and media maps.

## One-command use

```console
mgrb build taiwan-east --from 2022-01-01 --to 2026-08-23 \
  --actors plan,ccg,research,fishing --public-data --output paper,qgis,media
```

The shorter `mgrb build taiwan-east` selects area defaults. Use `taiwan-south` for the second v1
preset. MGRB chooses the LAEA display CRS, cartographic profile, bathymetry subset, adaptive page
orientation, map extent, layer order, restrained overlay basemap, and layout details. A live build
fails explicitly when a required public source cannot be obtained; `--offline` is for deterministic
CI and records unavailable layers instead of silently substituting data.

Local CSV, TSV, GeoJSON, GeoPackage, or Shapefile evidence may be supplied with repeated
`--local-data` options. Local input is processed in place and is not copied into the public
package. Its local reference and content hash are recorded in provenance without leaking the file.

## Evidence semantics

- Solid lines are dense observed AIS track segments within the configured gap threshold.
- Dash-dot lines are explicitly enabled, reproducible short-gap interpolations.
- Dashed lines are inferred connections between sparse observations, not observed routes.
- Square points are official observations.
- Halo markers indicate lower positional confidence, including map-derived positions.
- SAR, optical, and VIIRS detections do not establish identity merely through proximity.

An AIS gap is not automatically deliberate disabling. An unmatched SAR detection is not
automatically a “dark vessel.” Maritime-militia status is never inferred from appearance or
ordinary fishing behavior.

## Portable package

Each build contains `project/`, `data/`, `raw/`, `derived/`, `styles/`, `exports/`, and
`metadata/`. QGIS paths are relative. The QGIS gate copies the package to a second repository-local
location, reopens it, checks layer providers, and removes the temporary copy. Paper PDF/SVG/PNG
and 16:9 media PNG exports carry lineage sidecars; GeoPackages and bathymetry carry embedded MGRB
metadata.

The fixed layer tree separates public base, maritime jurisdiction, PLAN, CCG, research/survey,
fishing, events, and optional analytic layers. Empty or unavailable layers remain explicit. World
Bank shipping density is a large optional cache; MGRB never substitutes another product.

## Quality control

QC reports duplicate observations, invalid coordinates, timestamp disorder, impossible velocity,
large gaps, malformed identifiers, repeated points, missing time, and unresolved identity. It
writes cleaned/excluded points, gaps, flags, track segments, vessel summaries, and source evidence.
Large gaps are not repaired. Optional short interpolation is off by default and remains distinct
in data, style, and provenance.

Area presets extend the existing region model with a research flag, base region, title, bbox,
display CRS, profile, and default actors. Further regions can be added as configuration without
changing package architecture. Evidence adapters expose evidence types, access mode, licensing,
and redistribution status; future QGIS Processing or GUI front ends can construct the same build
request from a few research decisions.
