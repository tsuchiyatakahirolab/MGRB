# Known limitations in v1.0

MGRB v1.0 automates the public geospatial base, but several limits are intrinsic to the sources and should remain visible to users.

- Maritime-zone reference datasets do not by themselves establish legal entitlement or final delimitation. MGRB therefore preserves source and status metadata rather than treating a displayed line as self-authenticating.
- GEBCO is a global bathymetric compilation. Regional projects may require higher-resolution official or specialist bathymetry where available and appropriately licensed.
- Pacific-wide 0..360 derivatives are display/processing derivatives. Canonical geographic sources remain in their provider coordinate convention, and line geometries should use QGIS's geodesic antimeridian split before longitude shifting.
- Provider-gated or provider-controlled data are not mirrored merely for convenience. Users acquire those data under the provider's terms and ingest them locally.
- QGIS project generation is automated, but final publication figures still require scholarly judgement about extent, projection, feature selection and the status of the boundaries being shown.
