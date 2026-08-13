# MGRB v1.0 Cartography Specification

## Objective

MGRB must provide consistent, restrained, publication-grade maritime base maps that are useful for analysis rather than decorative presentation.

The cartographic system should replace repeated ad hoc decisions with scale-aware defaults.

## 1. Scale profiles

### Local / event

Purpose: detailed research maps for a bounded event or activity area, typically about 100–500 km across.

Prioritize:
- readable bathymetry;
- selected analytically meaningful contours;
- accurate coastline/islands;
- limited place labels;
- relevant maritime reference/status layers;
- space for future analytical overlays.

Avoid:
- dense national labels;
- excessive terrain texture;
- unnecessary administrative detail.

### Regional

Purpose: Taiwan, East Asian seas, Luzon Strait, Philippine Sea, East China Sea, South China Sea, or comparable regional context.

Prioritize:
- geographic orientation;
- major islands/coasts;
- restrained bathymetric relief;
- major trenches/ridges only where useful;
- reduced contour density;
- minimal labels.

### Theatre / Pacific

Purpose: Western Pacific and wider Pacific context, including antimeridian-crossing figures.

Prioritize:
- major basin/island-arc/trench structure;
- clean ocean/land separation;
- very sparse labels;
- robust projection and antimeridian handling.

Do not preserve local-scale detail at theatre scale.

## 2. Bathymetry

GEBCO is the canonical bathymetric source unless the repository source policy specifies otherwise.

Bathymetry must:
- use documented, versioned depth breaks or a documented continuous ramp;
- support selected contours independently of color;
- avoid high-saturation decorative ocean palettes;
- remain visually subordinate to future analytical layers;
- retain useful continental shelf/slope/trench information;
- be reproducible.

Suggested initial depth hierarchy, subject to render testing:
- 0 to -200 m;
- -200 to -1,000 m;
- -1,000 to -2,000 m;
- -2,000 to -4,000 m;
- -4,000 to -6,000 m;
- below -6,000 m.

The final implementation may refine these breaks if the rationale is documented.

## 3. Land, coastline, islands, and public context

Land should provide orientation without competing with ocean analysis.

Use the best approved public source for the region and scale. Natural Earth is one option, not a universal requirement.

The source-selection logic should allow MGRB to use or combine, as appropriate:
- GSHHG or equivalent higher-detail global coastlines;
- Natural Earth for small-scale/global context;
- official national/regional open geospatial data where it provides better authoritative or higher-resolution geometry;
- other approved public datasets recorded in the source registry.

Coastline source, width, and detail should vary by cartographic profile and geographic region. The chosen source and version must be recorded in provenance.

## 4. Maritime reference/status layers

Style categories according to data semantics.

Where status categories exist, distinguish them through some combination of:
- line pattern;
- line weight;
- opacity;
- hatching;
- labels.

Color alone is insufficient.

The map must not imply greater legal certainty than the underlying source/status metadata supports.

## 5. Labels

Labels must be sparse and scale-aware.

Prioritize only the place names necessary to interpret the research figure.

Avoid collisions and label clutter. Do not label every available feature.

## 6. Graticules, north arrow, scale bar

Use only when they improve interpretation.

Local/regional maps should normally include a useful scale indication. Pacific-wide figures may rely more on graticules and projection context.

## 7. Layout hierarchy

The map is primary.

Title, legend, scale, and source/provenance footer should be visually secondary and consistent.

Layouts must work at common journal figure widths.

## 8. Publication outputs

Generate stable PDF and PNG outputs. Provide SVG where supported without breaking map appearance.

Test:
- normal color;
- grayscale/print-safe;
- single-column-scale legibility;
- double-column-scale legibility.

## 9. Analytical-overlay readiness

MGRB outputs must leave sufficient visual contrast for future user-supplied analytical layers.

Do not bake analytical-layer styles into the public MGRB cartographic core.

## 10. Color customization

The canonical MGRB palette is a versioned default, not an immutable identity.

All presentation colors must be configurable through the theme system in `COLOR_SYSTEM_SPEC.md`.

Changing color must not alter:
- depth semantics;
- legal/status semantics;
- geometry;
- source provenance;
- MGRB lineage.
