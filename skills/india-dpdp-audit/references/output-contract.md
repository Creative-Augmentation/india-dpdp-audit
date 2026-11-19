# Structured audit records

Use one JSON file for the complete audit and share a rendered Markdown report when useful. The [schema](../assets/audit.schema.json) describes the v1 record. The [synthetic example](../assets/example-audit.json) records a Shopify checkout and a custom support journey. The [synthetic control](../assets/example-control-audit.json) shows how unknown, supplied and inferred evidence produce open questions and zero observed gaps.

Run from the repository root with Python 3.10 or newer. Install the dependency in a virtual environment. The commands use the schema packaged with the script and work with the entire skill folder copied elsewhere.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r skills/india-dpdp-audit/scripts/requirements.txt
python skills/india-dpdp-audit/scripts/audit.py validate audit.json
python skills/india-dpdp-audit/scripts/audit.py render audit.json > audit.md
python skills/india-dpdp-audit/scripts/audit.py diff audit.json followup.json
```

Every command validates its inputs and exits with a path-qualified diagnostic on failure. The CLI reads UTF-8 JSON with or without a byte-order mark, leaves input files untouched, and uses standard output for results. Install the packaged requirements to enable date and time validation. Rendering keeps link-shaped text in literal code spans so GFM displays it without activating a link. It retains combining marks and joiners used in Indic scripts while removing directional overrides and other invisible control characters.

The diff lists scope fields and records added, removed, or changed by stable ID. Reordering reference IDs does not count as a change. A subject or authorized-domain change produces a scope warning. A removed gap or unverified finding produces a closure warning because it has no linked follow-up evidence. An upgrade from either status to a sampled success or an exclusion produces a warning unless the later finding links new direct evidence captured after the earlier audit date. A new ID and capture time for an earlier kind, locator and observation do not establish fresh evidence. This check compares record content. Reviewers still verify provenance and whether the new observation establishes closure.

## Read the summary

The report opens with observed gaps, checks the auditor could not complete, sampled successes, journey coverage and next actions. Gap entries carry priority, legal timing and applicability. The summary counts recorded entries and shows a bounded preview, the audit window, the oldest linked evidence date when available, and the reason for an extended window. The open-questions list shows what could not be verified and the next step for each open check. The detailed sections retain the full record, evidence, legal dates and action verification steps.

Journey counts use the recorded journeys as their denominator. An empty coverage list means the audit has no recorded journey coverage to assess. Blocked and uninspected journeys remain visible even when there are no findings. Overall compliance remains undetermined, including when every recorded journey was inspected or the only findings are sampled successes. The schema has no overall compliance or certification field.

## Record the audit

- **Scope.** Set `schema_version` to `"1.0"` and use the audit calendar date in India. Set `audit_window_start` to the first day of evidence gathering for a multi-day audit. It defaults to the audit date. The window includes both dates and can span up to 31 days by default. Supply a nonempty `audit_window_reason` to explain a longer window. Record the authorized modes, exact lower-case domain names, platforms, limitations, and authorized repository locators and pinned revisions where repository inspection is in scope. List any subdomains inspected explicitly. Staging and internal modes require their own authorization. Authorization comes from the audit brief. Domain and revision checks compare the record to its declared scope.
- **Journey coverage.** Record inspected, blocked and uninspected journeys with notes that explain what happened. Inspected journeys require direct evidence. Record known blocked or uninspected journeys even if the audit could not begin. Use an empty list only when no journeys were recorded. Use a distinct journey for an internal step where a public review covers only the earlier collection step.
- **Evidence.** Give each item a globally unique, stable ID, type, status, capture time with offset, locator, and narrow observation. Choose the evidence status using the tiers below. A repository item needs the authorized locator and revision in addition to a file and line in its evidence locator. For public items, cite the authorized page or captured public source URL as the locator and describe any third-party endpoint mentioned in the evidence. Use `internal_record` for a directly inspected configuration, export, log, contract or test artifact with a locator and a specific observation. Use redacted excerpts or locators. Keep personal data, secrets, credentials and raw operational records out of the record.
- **Data map.** Link each flow to its journey. Record evidence-backed observations, owner-stated purpose and claimed ground, and unknowns independently. Evidence that data collection occurs establishes the collection step only. Claims about downstream retention or sharing require their own evidence.
- **Legal ledger.** Keep one status per entry. Record the official source URL, provision, date of access, publication date, legal status and reasoning. Use a null date for an unresolved effective or publication date and explain the uncertainty in the notes. Every future duty needs an exact `effective_on` date, a supported latest `effective_by` date, or a conservative `preparation_on` date. A future duty can have an unresolved exact commencement date when the sources establish that it has yet to commence. Where appropriate, record a separate conservative `preparation_on` date and explain its basis in notes. Re-verify a future duty against official sources after its preparation date or update the status as the evidence warrants. The preparation date provides a review trigger rather than an effective date. A `current` entry requires an effective date on or before the audit date. If the exact day remains unresolved but all supported readings place commencement on or before the audit date, leave `effective_on` null, set `effective_by` to the latest supported date, and explain the readings and sources in the notes. Use `uncertain` where the status itself is unresolved. Use citation-only provisions for DPDP Act and Rules entries so the local commencement map can check the phase. Split provisions from different phases into separate entries, or record the status as uncertain with no single commencement date. The pinned map checks only the included commencement provisions. Verify and interpret the sources separately using the [legal baseline](legal-baseline.md) and current official material.
- **Findings.** Use evidence status, applicability and legal status independently. An observed control gap can coexist with unknown legal applicability. Explain the uncertainty in the applicability reason and link the appropriate ledger entries. Findings based on legal duties link ledger entries with the same legal status. Split findings when different commencement phases apply to different duties. Use `good_practice` for an engineering or process recommendation with no linked legal classification. Give each finding its own scope, priority, confidence and evidence. A sampled success or exclusion may cite only direct evidence from sources other than an owner statement, captured within the audit window in the India time zone. A historical observed gap may remain recorded with dated evidence while retesting is pending. Put limited evidence and owner statements in the appropriate contextual sections. Reviewers still decide whether the evidence supports the specific finding.
- **Actions.** Link actions to one or more findings and give each action an owner role, target location, effort estimate or stated unknown, actionable acceptance criteria, prerequisites, verification steps and verification mode. Every observed gap and unverified finding needs a linked action. Use `evidence_request` for an unverified finding. Use `remediation` when an observed issue supports a change. A follow-up pending access can specify a verification mode beyond the present audit scope. Mark an action verified only when evidence in the required mode directly supports its acceptance criteria and prerequisites are verified. For an observed gap or unverified finding with baseline evidence, add later verification evidence before marking the action verified.

## Evidence labels

| Evidence tier | Record it as |
| --- | --- |
| Observed | `direct` evidence of a specific page, network event, code path, configuration or record inspected in this audit. A gap must cite an observation that shows the defect itself. |
| Supplied | `owner_statement` with status `asserted` for an unverified owner claim or document. Use `not_verified` and request corroboration when it is the sole basis for a check. |
| Inferred | `inferred` evidence derived from other evidence. Name the underlying evidence in the observation and use it for a watch note under `not_verified`. |
| Unknown | `not_verified` with no supporting evidence or with `limited` evidence for incomplete or inconclusive material. State what could not be verified and request the next piece of evidence. |

Use the finding evidence status to distinguish the results below. Leave claims that a check is compliant or has no gaps out of unverified items and audit-wide scope statements while checks remain open.

| Label | Evidence needed |
| --- | --- |
| `observed_gap` | Direct evidence of a specific gap in the sampled surface. Applicability and effective status govern the legal interpretation. |
| `not_verified` | An unresolved check due to incomplete evidence or access. Record the reason and request the evidence that resolves it. |
| `meets_sampled_check` | Direct evidence supporting the stated control in a bounded sample. |
| `not_applicable` | Direct evidence and a stated reason supporting exclusion in the sampled context. Applicability must also be `not_applicable`. |

## Severity

Rate observed gaps by their demonstrated impact and keep legal timing and applicability separate.

High and critical priorities require linked direct evidence. Version 1.0 records with a `high` `not_verified` finding now fail validation.

| Priority | Observable test |
| --- | --- |
| Critical | The observation shows harm directly. For example, an unauthenticated response exposes personal data, or a network capture shows personal-data processing continuing after the visitor refused it. |
| High | The observation shows actual personal-data exposure or processing without the required safeguard and establishes a material consequence, such as routine collection in a sampled journey without its required notice. |
| Medium | The sampled surface shows a concrete control defect with bounded impact, such as a required field with no stated purpose in the sampled form. |
| Low | The sample shows a specific defect with minor impact, such as an outdated label that leaves the privacy action accessible. |

Use `informational` for watch notes. The validator checks evidence links, dates and formats, evidence and status relationships, scope references, and action prerequisites. Reviewers verify provenance, whether observations establish the specific defect and impact, whether legal sources are authoritative and current, whether parties authorized each inspection, and whether evidence satisfies the acceptance criteria.
