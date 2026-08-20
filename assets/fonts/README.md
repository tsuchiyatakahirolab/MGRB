# Bundled release font

MGRB bundles Noto Sans Regular and Bold v2.015 under the SIL Open Font License 1.1.
The files are sourced from the official `notofonts/latin-greek-cyrillic` release.

Headless QGIS packages may expose an empty Qt font database. MGRB therefore registers
these pinned files explicitly before creating labels or layouts, verifies required
glyph coverage and distinct glyph rendering, and scans the actual exported PNG text
regions for repeated missing-glyph (tofu) blocks.
