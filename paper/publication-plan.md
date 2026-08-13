# MGRB publication plan

## Recommended route: publish the software metapaper early

1. Publish the GitHub repository and tag MGRB v1.0.0 after all release gates pass.
2. Archive the exact release in a preservation repository and obtain a version DOI.
3. Update `CITATION.cff`, README and the website resource page with the DOI.
4. Submit a Journal of Open Research Software (JORS) Software Metapaper once the public release is independently installable and reviewable.
5. Use the software-paper citation as the canonical scholarly reference while continuing version-specific software releases and DOI archives.
6. Publish substantive maritime studies separately; those papers should cite the MGRB software paper and the exact software release used.

## Alternative route: wait for JOSS

If JOSS is preferred instead of JORS, do not submit immediately. Maintain the repository publicly, release iteratively, collect documented research use and external adoption, and submit only after satisfying JOSS's then-current public-development-history and research-impact gates. As of August 2026 those gates require more than six months of public development history and demonstrated research impact.

JORS and JOSS should be treated as alternative software-publication routes unless the later submission represents materially distinct software and the relevant editors confirm that publication is appropriate.

## Distinct later publication

A later methodological article can address substantive questions that are not the software metapaper itself, such as how projection choice, antimeridian handling, bathymetric scale and maritime-boundary uncertainty affect inference and reproducibility in maritime geospatial research. Such a paper should contain empirical comparison or methodological evaluation rather than repeat the software description.
