# CI

`.github/workflows/validate.yml` is the hosted check. It is deliberately light: one job on `ubuntu-latest`, Python 3.10 (the lowest supported version), no matrix, `pull_request` only, no path filters, a 5-minute timeout and a per-PR concurrency group that cancels superseded runs.

Steps: install the packaged and test requirements (pip cached), run `python -m unittest discover -s tests`, then `python scripts/check_fixture_hygiene.py`.

CI installs no browser, and the tests run without one. The benchmark runner and example render run separately from CI. Run those locally when you change them.

Its only GitHub permission is `contents: read`; action revisions are pinned by SHA. It uses synthetic inputs only, never customer sites, and uploads no audit records.
