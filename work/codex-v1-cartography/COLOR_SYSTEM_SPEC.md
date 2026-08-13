# MGRB v1.0 Color and Theme System

## Principle

Color is a configurable cartographic parameter.

Researchers must be able to adjust presentation for a journal, book, web page, grayscale print, presentation, or house style without editing core MGRB implementation files.

A color-adjusted output remains an MGRB-derived build and must retain explicit provenance.

## Required structure

Implement version-controlled canonical themes and support an external user theme.

A reasonable structure is:

```text
config/
  themes/
    canonical.yml
    grayscale.yml
    print-muted.yml
    media.yml
```

Also provide a documented example custom theme.

Equivalent structure is acceptable if the same separation is preserved.

## Required adjustable properties

At minimum, expose configurable presentation values for:
- bathymetry ramp/classes;
- land fill;
- coastline;
- contour lines;
- hillshade/relief opacity and blend controls where used;
- maritime reference/status layer colors;
- uncertainty/dispute colors;
- graticule;
- labels;
- legend/layout background where relevant.

Do not put analytical-layer colors into the public MGRB core.

## Semantic separation

Depth breaks, contour levels, maritime status categories, uncertainty categories, and other analytical semantics must be stored independently from hue.

Changing a theme must not change the underlying category.

Where meaning matters, support non-color encodings such as:
- dash patterns;
- line weight;
- hatching;
- opacity;
- symbols.

This must remain interpretable in grayscale.

## Custom-theme interface

Support a documented mechanism equivalent to:

```text
mgrb build taiwan_east_south --profile local --theme canonical
mgrb build taiwan_east_south --profile local --theme /path/to/custom-theme.yml
```

Exact command syntax may follow the repository's CLI conventions.

A custom theme must not require editing canonical QML, Python, or source registry files.

## Resolved theme

For every build, resolve defaults plus overrides into one deterministic theme object.

Write the resolved theme or equivalent machine-readable record to build metadata, for example:

```text
metadata/resolved-theme.yml
metadata/style-manifest.json
```

## Provenance fields

Record at least:
- `style_system: MGRB`;
- style schema version;
- MGRB version;
- cartographic profile;
- layout profile;
- `palette_id`;
- `palette_origin: canonical|custom`;
- deterministic `palette_sha256`;
- `style_overrides: true|false`.

Do not include private absolute filesystem paths in public exports.

## Derivatives

Changing:
- color;
- line weight within supported theme parameters;
- typography within supported layout parameters;
- background tone;

does not create a new geospatial base.

Documentation must make clear that presentation customization is supported while MGRB citation/provenance remains applicable.

## Integrity

Do not use:
- hidden watermarks;
- fabricated geography;
- trap data;
- intentionally wrong coordinates;
- deceptive fingerprints.

Protection comes from explicit versioning, provenance, deterministic builds, metadata, release history, and citation.

## Tests

Test that:
- all canonical themes resolve;
- a custom theme resolves;
- invalid theme values fail clearly;
- partial overrides inherit documented defaults;
- theme hashes are deterministic;
- custom themes do not mutate core styles;
- semantics remain stable across themes;
- build metadata records the resolved theme;
- grayscale remains interpretable.
