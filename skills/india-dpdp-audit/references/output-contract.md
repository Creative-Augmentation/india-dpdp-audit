# Structured audit records

Use one JSON file for the complete audit and share a rendered Markdown report when useful. The [schema](../assets/audit.schema.json) describes the v1 record. The [synthetic example](../assets/example-audit.json) records a Shopify checkout and a custom support journey and shows how to carry unresolved questions forward.

Run from the repository root with Python 3.10 or newer. Install the dependency in a virtual environment. The commands use the schema packaged with the script and work with the entire skill folder copied elsewhere.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r skills/india-dpdp-audit/scripts/requirements.txt
python skills/india-dpdp-audit/scripts/audit.py validate audit.json
python skills/india-dpdp-audit/scripts/audit.py render audit.json > audit.md
python skills/india-dpdp-audit/scripts/audit.py diff audit.json followup.json
```

Every command validates its inputs and exits with a diagnostic on failure. The CLI works on local files, leaves input files untouched, and uses standard output for results. Rendering treats record text and URLs as literal text. The diff lists scope fields and records added, removed, or changed by stable ID. A removed finding is a record difference and requires separate evidence to establish closure.

## Record the audit

- **Scope.** Set `schema_version` to `"1.0"` and use the audit calendar date in India. Record the authorized modes, exact lower-case domain names, platforms, limitations, and authorized repository locators and pinned revisions where repository inspection is in scope. List any subdomains inspected explicitly. Staging and internal modes require their own authorization. Authorization comes from the audit brief. Domain and revision checks compare the record to its declared scope.
- **Journey coverage.** Record inspected, blocked and uninspected journeys with notes that explain what happened. Inspected journeys require direct evidence. Use a distinct journey for an internal step where a public review covers only the earlier collection step.
- **Evidence.** Give each item a globally unique, stable ID, type, status, capture time with offset, locator, and narrow observation. Use `direct` for evidence that supports the stated observation and `limited` for partial, inconclusive, or unavailable evidence. A repository item needs the authorized locator and revision in addition to a file and line in its evidence locator. For public items, cite the authorized page or captured public source URL as the locator and describe any third-party endpoint mentioned in the evidence. Record owner statements as `asserted`; they supply context and claims. Use redacted excerpts or locators. Keep personal data, secrets, credentials and raw operational records out of the record.
- **Data map.** Link each flow to its journey. Record evidence-backed observations, owner-stated purpose and claimed ground, and unknowns independently. Evidence that data collection occurs establishes the collection step only. Claims about downstream retention or sharing require their own evidence.
- **Legal ledger.** Keep one status per entry. Record the official source URL, provision, date of access, publication date, legal status and reasoning. Use a null date for an unresolved effective or publication date and explain the uncertainty in the notes. A future duty can have an unresolved exact commencement date when the sources establish that it has yet to commence. Where appropriate, record a separate conservative `preparation_on` date and explain its basis in notes. A `current` entry requires an effective date on or before the audit date. If the exact day remains unresolved but all supported readings place commencement on or before the audit date, leave `effective_on` null, set `effective_by` to the latest supported date, and explain the readings and sources in the notes. Use `uncertain` where the status itself is unresolved. Verify and interpret the sources separately using the [legal baseline](legal-baseline.md) and current official material.
- **Findings.** Use evidence status, applicability and legal status independently. An observed control gap can coexist with unknown legal applicability. Explain the uncertainty in the applicability reason and link the appropriate ledger entries. Findings based on legal duties link ledger entries with the same legal status. Split findings when different commencement phases apply to different duties. Use `good_practice` for an engineering or process recommendation with no linked legal classification. Give each finding its own scope, priority, confidence and evidence.
- **Actions.** Link actions to one or more findings and give each action an owner role, target location, effort estimate or stated unknown, actionable acceptance criteria, prerequisites, verification steps and verification mode. Every observed gap and unverified finding needs a linked action. Use `evidence_request` for an unverified finding. Use `remediation` when an observed issue supports a change. A follow-up pending access can specify a verification mode beyond the present audit scope. Mark an action verified only when evidence in the required mode directly supports its acceptance criteria and prerequisites are verified. For an observed gap or unverified finding with baseline evidence, add later verification evidence before marking the action verified.

## Evidence labels

| Label | Evidence needed |
| --- | --- |
| `observed_gap` | Direct evidence of a specific gap in the sampled surface. Applicability and effective status govern the legal interpretation. |
| `not_verified` | An unresolved check due to incomplete evidence or access. Record the reason and request the evidence that resolves it. |
| `meets_sampled_check` | Direct evidence supporting the stated control in a bounded sample. |
| `not_applicable` | Direct evidence and a stated reason supporting exclusion in the sampled context. Applicability must also be `not_applicable`. |

Dates and formats, evidence and status relationships, ID and domain references, and action prerequisites are checked mechanically. Reviewers still decide whether observations support their claims, whether legal sources are authoritative and current, whether parties authorized each inspection, and whether verification evidence meets the acceptance criteria. Use the output as a technical and readiness review with these limits.
