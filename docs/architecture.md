# Architecture

MGRB separates five layers of responsibility.

1. **Source registry:** records upstream provider, version, citation, licence and acquisition method.
2. **Canonical source layer:** preserves provider geometry and coordinate conventions.
3. **Derived geospatial layer:** clips, normalizes, reprojects or wraps data for a declared study region.
4. **QGIS project layer:** applies consistent grouping, symbology, projection and publication layout.
5. **Provenance layer:** records MGRB version, Git commit, transformations and SHA-256 file hashes.

This separation allows a figure to be regenerated without treating a visually convenient boundary as a legally authoritative one or losing the origin of a derived dataset.
