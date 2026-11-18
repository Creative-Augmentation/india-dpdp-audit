# CI activation pending

`validate-audit.yml` is the proposed GitHub Actions workflow for Python 3.10 and 3.14. It is deliberately stored outside `.github/workflows/` and does not run in this location.

Hosted checks are pending. All 70 tests and copied-package validation/rendering passed locally on Python 3.10.19 and 3.14.7 on 18 November 2026. Local validation is recorded separately in the review handoff; it does not establish that GitHub Actions has run.

A maintainer with workflow permission can activate this template at `.github/workflows/ci.yml` in a subsequent commit. It pins action revisions, installs the packaged dependencies, runs unit tests, validates benchmark fixtures, checks fixture hygiene and validates/renders the synthetic example. Its only GitHub permission is `contents: read`; it never scans customer websites or uploads audit records.
