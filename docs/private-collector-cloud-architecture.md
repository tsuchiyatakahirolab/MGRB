# Future private collector cloud architecture (non-v1 implementation note)

The validated local GFW UI collector is private operational infrastructure and is excluded
from MGRB v1.0. A future migration could use a dedicated persistent virtual machine with an
interactive desktop, encrypted disk, restricted operator access, a bounded daily scheduler,
and a private durable archive. The owner would establish and periodically renew the normal
provider session interactively; automation would only verify an existing authenticated
session and fail closed on reauthentication, MFA, CAPTCHA, Terms, UI ambiguity, or download
failure.

The public MGRB repository would remain separate. Only generic import schemas and adapters
belong here. Browser profiles, cookies, session state, raw vessel tracks, acquisition SQLite,
and derived private GeoPackages would stay in separately controlled storage. A later design
must define key management, backup/retention, monitoring, provider-policy review, cost limits,
and an explicit owner-approved commissioning procedure before any cloud resource is created.

No cloud resource is deployed and no browser/session secret is copied by the v1.0 release
candidate.
