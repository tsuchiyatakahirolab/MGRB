# MGRB local product interface

MGRB v1.0 asks for research choices and resolves routine GIS engineering automatically. The
local interface is a thin layer over the same deterministic Python and headless QGIS build
used by the CLI; it is not a second renderer.

## Start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\mgrb.exe ui
```

The service binds to `127.0.0.1` by default and opens a local browser. It does not upload user
files to MGRB or a cloud service. Uploaded working copies remain under the ignored `.tmp/`
directory. Generated packages go to `build/products/` unless `--output-root` is supplied.

## Main choices

- Area: Taiwan East, Taiwan South, Taiwan Strait, Bashi/Luzon Strait, East China Sea,
  South China Sea, Western Pacific, Pacific, the public Xue Long demo, or a custom bbox.
- Background: clean publication, bathymetry, bathymetry plus relief, minimal grayscale,
  navigation/context, optional imagery reference, or none.
- Maritime layers: territorial sea, contiguous zone, EEZ/reference EEZ, source-specific
  boundary, continental shelf, computed median/equidistance reference, or a custom layer.
- Input: CSV, TSV, GeoJSON, GeoPackage, and Shapefile point datasets.
- Output: interactive selection preview, paper map, media map, and portable QGIS package.

The primary screen does not ask users to choose CRS, raster resolution, coastline detail,
antimeridian handling, label density, contour levels, page orientation, or source footer.
Those defaults resolve from the selected area and profile.

## Schema inspection and QC

MGRB recognizes common latitude, longitude, timestamp, MMSI, IMO, vessel-name, ID, speed,
course, heading, depth, and `seg_id` fields. It never silently resolves an ambiguous critical
field. When confirmation is needed, the UI displays a small mapping form.

The compact QC result reports valid positions, gaps over six hours, and generated segments.
Full CSV audit files in the package record invalid coordinates/timestamps, duplicates,
impossible speeds, gaps, excluded positions, and per-entity coverage.

Timestamped vessel positions are segmented as observed tracks only within the configured
maximum gap. Provider `seg_id` changes always split the MGRB segment. Sparse official
observations remain points or explicitly inferred connections; they are never promoted to
raw position tracks.

## CLI equivalent

```powershell
mgrb build taiwan-east `
  --background bathymetry `
  --maritime-layers eez_reference,territorial_sea `
  --input .\vessel.csv `
  --output-root .\build\products `
  --output-name my-research-map
```

The package contains relative-path QGIS data, paper PDF/SVG/PNG, a separate media PNG,
an 85 mm journal preview, machine-readable provenance, source and style manifests, hashes,
and an archive beside the package directory.

## Median/equidistance references

The advanced CLI can generate a reproducible local reference from two documented baseline
layers:

```powershell
mgrb median-line baseline-a.gpkg baseline-b.gpkg computed.gpkg `
  --crs "+proj=laea +lat_0=23 +lon_0=122 +datum=WGS84 +units=m"
```

The output records both input names, computation CRS, sampling/tolerance parameters,
timestamp, method, and `legal_status=COMPUTED_REFERENCE`. It is explicitly labelled as a
computed cartographic reference, not as an agreed international boundary.

## Optional imagery

Satellite/imagery is a provider-configuration slot, not a bundled universal basemap. It must
retain provider terms and fail clearly when the configured network service is unavailable.
No external imagery is silently substituted.
