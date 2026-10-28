# Security Policy

SAHAKAR–SEVA is a hackathon-stage project. It is **not production software** and should not be
used to process real payments or real personal data. See
[`docs/SECURITY_AND_TRUST_MODEL.md`](docs/SECURITY_AND_TRUST_MODEL.md) for the full trust model and
the current list of risks that still await production controls.

## Reporting a vulnerability

Please report suspected vulnerabilities **privately**, not through public issues or pull requests.

- Preferred: open a private [GitHub Security Advisory](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  on this repository ("Security" tab → "Report a vulnerability"). This keeps the report confidential
  until a fix is ready.
- Alternative: contact the repository owner directly through their GitHub profile.

> This project does not publish a dedicated security email address. Do not assume one exists; use the
> private advisory channel above.

When reporting, please include:

- a description of the issue and its impact,
- the affected component (frontend, API, database, trust ledger, anchoring, CI),
- steps to reproduce, and
- any relevant logs or proof-of-concept (with secrets redacted).

Please allow a reasonable period for triage and remediation before any public disclosure.

## Scope

In scope: the application code in `apps/web` and `services/api`, database migrations, the trust/ledger
and anchoring implementation, the demo seeder, and the CI workflow.

Out of scope: third-party services (Supabase, the DigiCert public TSA), and the known, documented
limitations listed in `docs/SECURITY_AND_TRUST_MODEL.md` (for example: payments are simulated, and
local development authentication is intentionally not production identity verification).

## Secrets

No secrets are committed to this repository. `.env` files are git-ignored. If you believe a secret was
committed, treat it as compromised: report it privately and rotate/revoke the credential immediately.
Never attach real secrets, tokens, or personal data to a report.
