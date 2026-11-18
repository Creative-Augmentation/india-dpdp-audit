# CI activation pending

`validate-audit.yml` is the proposed GitHub Actions workflow for Python 3.10 and 3.14. It is deliberately stored outside `.github/workflows/` and does not run in this location.

The feature-branch publisher could not create `.github/workflows/ci.yml`: GitHub rejected the push because its OAuth token lacks `workflow` scope. The implementation and synthetic checks can still be reviewed. Local tests passed on Python 3.14; hosted validation, including Python 3.10, remains pending.

A maintainer with workflow permission can activate this exact template at `.github/workflows/ci.yml` in a subsequent commit. It installs the packaged validation dependencies, runs the unit tests and validates/renders the synthetic example. Its only GitHub permission is `contents: read`; it never scans customer websites or uploads audit records.
