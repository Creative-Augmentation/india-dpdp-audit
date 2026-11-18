# india-dpdp-audit

An AI-agent skill for evidence-based Indian DPDP website audits and practical remediation plans. It supports Shopify, WooCommerce, Firebase and custom stacks, including mixed stacks. Version **0.2.0** adds a structured audit record and an optional local validation/reporting helper.

The agent inspects authorised evidence and proposes work. The helper validates and formats that record; it does not browse, scan a website, decide legal applicability or certify compliance.

## Audit to implementation plan

1. Record the audit date, authorised domains, permitted modes and sampled journeys.
2. Gather public observations and, where authorised, source/configuration and operational evidence. Keep owner statements separate from observations.
3. Map findings to current official legal sources, applicability and commencement status.
4. Produce concrete fixes or evidence requests with owners, dependencies and acceptance criteria.
5. Retest within the permitted scope and attach evidence before recording verification.

Reports preserve **Observed gap**, **Not verified**, **Meets sampled check** and **Not applicable**. Evidence status, legal status and practical priority remain separate. No overall compliance score is generated.

Rendered reports start with a short summary of gaps, checks that could not be completed, sampled successes and next actions. Journey coverage counts refer only to the recorded sample; overall compliance remains undetermined.

**Not legal advice or certification.** Audit only sites and repositories you own or are authorised to inspect. See [DISCLAIMER.md](DISCLAIMER.md). Public-only work cannot establish backend deletion, contracts or operational controls.

## Install and use the skill

Copy the **entire** `skills/india-dpdp-audit/` folder, including its references, assets, scripts and licence. The normal audit workflow needs an agent with suitable browsing or repository tools; it does not require the Python helper.

| Tool | Guide |
|---|---|
| Claude Code | [Install](docs/install-claude-code.md) |
| OpenAI Codex CLI | [Install](docs/install-codex.md) |
| Grok Build CLI | [Install](docs/install-grok-cli.md) |
| Cursor | [Install](docs/install-cursor.md) |

Those guides retain their recorded verification limits; this release does not claim a fresh runtime test of all four hosts.

Example request:

> Use india-dpdp-audit to review https://shop.example (I own this site). Public observation only; do not submit forms or create accounts. Sample storefront, contact, checkout entry and privacy journeys. Apply the relevant platform playbooks, distinguish unknowns from observed gaps, and draft a prioritised implementation plan with acceptance criteria. Produce a structured audit record for handoff.

The skill routes to [generic](skills/india-dpdp-audit/references/platforms/generic.md), [Shopify](skills/india-dpdp-audit/references/platforms/shopify.md), [WooCommerce](skills/india-dpdp-audit/references/platforms/woocommerce.md) and [Firebase](skills/india-dpdp-audit/references/platforms/firebase.md) checks. [Owner questions](skills/india-dpdp-audit/references/owner-questions.md) fill material evidence gaps without requesting customer exports.

## Try the local helper

Python 3.10+ is required. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r skills/india-dpdp-audit/scripts/requirements.txt
.venv/bin/python skills/india-dpdp-audit/scripts/audit.py validate skills/india-dpdp-audit/assets/example-audit.json
.venv/bin/python skills/india-dpdp-audit/scripts/audit.py render skills/india-dpdp-audit/assets/example-audit.json
```

On Windows, use `.venv\Scripts\python.exe`. After installation, the helper works offline. It reads local JSON and prints validation, Markdown or a JSON comparison to standard output. It does not upload records or edit the audited site. Shell redirection may be used to save a report privately.

```sh
.venv/bin/python skills/india-dpdp-audit/scripts/audit.py diff earlier-audit.json later-audit.json
```

The comparison reports added, removed and changed records; removal does not establish remediation. Validation checks schema and cross-record consistency, not whether an observation is true or a legal source is authoritative. See the [output contract](skills/india-dpdp-audit/references/output-contract.md), [JSON Schema](skills/india-dpdp-audit/assets/audit.schema.json), and optional [report](skills/india-dpdp-audit/assets/report-template.md) / [remediation](skills/india-dpdp-audit/assets/remediation-template.md) templates.

The example is synthetic. Keep real audit records outside this public repository; ignored output directories are convenience, not a privacy control.

## Legal freshness

[Legal-source review](skills/india-dpdp-audit/references/legal-baseline.md): 18 November 2026. The November 2026 registration phase date has passed under both calendar readings recorded there. Most substantive processing duties remain in the May 2027 phase under the instruments reviewed. Recheck applicable notifications for each audit; the review has source-access and publication-date limitations.

A cookie, public Firebase client key, foreign host or missing public backend evidence does not by itself establish a violation. The skill does not impose a universal cookie banner, DPO or India-only hosting requirement.

## Development and evaluation

```sh
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Tests check the output contract, inconsistent evidence/status combinations, safe rendering and CLI behaviour. The [synthetic evaluation packets](evals/README.md) are prepared for agent runs; the full set has not yet been run. A separate [exploratory forward test](evals/results/2026-11-18-copper.md) records its narrow result. Unit-test success does not establish agent accuracy. The [CI template](ci/README.md) targets Python 3.10 and 3.14 using synthetic inputs, never customer sites; it is not active yet.

The [benchmark coverage](docs/benchmark-coverage.md) adds 24 public development packets and reserves eight private cases for independent Opus evaluation. Public expected answers support regression work, not independent accuracy claims. The [phased plan](docs/PHASED_BUILD_PLAN.md) records the approved foundation/benchmark work and the next priority: an actual evidence collector and merchant command.

[Research and design](docs/research-and-design.md) records upstream inspiration and the next collector evaluation. No upstream scanner is bundled or invoked in this release. [Contributing](CONTRIBUTING.md) and [refreshing copies](REFRESH.md) describe the maintained source.

## Licence and contact

The current licence is [PolyForm Noncommercial 1.0.0](LICENSE). **Business use, including auditing a for-profit merchant's own store, needs separate permission.** Selling audits or offering a paid product also needs permission. Open a GitHub Issue for general questions; never include personal data, credentials or private site evidence. See [SECURITY.md](SECURITY.md).

A [custom self-use licence proposal](docs/licensing/CUSTOM_SELF_USE_LICENSE_DRAFT.md) would allow businesses to audit their own systems while reserving agency services and resale. It awaits owner approval and grants no additional rights at present. The [compatibility note](docs/licensing/UPSTREAM_COMPATIBILITY.md) covers the boundaries for possible upstream reuse.

Required Notice: Copyright (c) 2026 Creative Augmentation
