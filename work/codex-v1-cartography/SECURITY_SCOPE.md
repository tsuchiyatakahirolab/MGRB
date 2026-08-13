# Public Repository Scope

MGRB v1.0 is a public geospatial base built from public-source geographic data.

The public repository must contain no licensed or non-public analytical material.

## Prohibited content

Do not add:
- ingeniSPACE AIS data;
- ingeniSPACE SAR data or derived intelligence;
- other licensed vessel-level data;
- vessel identifiers collected for current research;
- anomaly candidates;
- anomaly-detection models tied to private research;
- private case libraries;
- unpublished research findings;
- internal research-group notes;
- operational or intelligence assessments.

Do not create placeholder directories whose names reveal such private research workflows.

## Allowed examples

Examples and tests must use:
- public geographic base data;
- synthetic/non-sensitive dummy analytical geometry only when a test requires it;
- generic names that do not encode current research targets.

Synthetic test data must be obviously synthetic and never mixed into canonical geographic data.

## Build logs

Public build logs and manifests must not leak:
- local usernames;
- private absolute paths;
- credentials;
- tokens;
- proprietary data locations.
