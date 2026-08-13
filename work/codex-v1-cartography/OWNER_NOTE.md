# Owner Note

The immediate purpose of MGRB v1.0 is to remove background-map construction as a recurring burden in maritime research.

The system should be usable before the ingeniSPACE hands-on session so that licensed AIS/SAR or other research data can later be added in a separate non-public analytical environment.

Priority order:

1. Correct geography and reproducible data handling.
2. Correct projection and antimeridian behavior.
3. Accurate source/status/provenance treatment.
4. Strong scale-aware cartographic design.
5. Flexible color/theme customization.
6. Publication-ready export.
7. Ease of reuse.

Color must remain adjustable within MGRB. Researchers should be free to tune presentation without editing the core system. Such changes must preserve explicit MGRB version/theme provenance.

Do not optimize the public repository around a specific country, vessel, or current research case.


## Public context sources

Natural Earth is not the MGRB identity and must not become a hard-coded dependency for all map context. The platform should choose the best public, citable source by region and scale. Global small-scale context may use Natural Earth, while higher-detail coastlines or official regional/national datasets may be preferable elsewhere. The source registry and provenance system should make those choices explicit and reproducible.
