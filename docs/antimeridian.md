# Antimeridian handling

Canonical source coordinates remain in their provider coordinate system, normally WGS84 longitude from -180° to 180°. MGRB does not permanently alter canonical source geometry merely to create a continuous Pacific map.

For Pacific-wide work, MGRB provides two complementary methods.

## Display method

Use a Pacific-centred projection, normally with a central meridian of 180°. QGIS performs on-the-fly reprojection for ordinary layers. Line geometries that cross ±180° should first use QGIS `native:antimeridiansplit`, which calculates the breakpoint geodesically.

## Continuous-longitude derivative

Algorithms that require a continuous Pacific longitude domain may use a generated 0–360° derivative. The derivative is stored separately from the canonical source and its transformation is recorded in provenance metadata. Raster derivatives split the canonical source window at ±180°, shift the western-hemisphere component by +360°, and mosaic the parts.

The 0–360° derivative is an analytical convenience, not a replacement for canonical source coordinates.
