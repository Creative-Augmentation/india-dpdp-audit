# Offline DPDP benchmark

This harness validates synthetic evidence packets and scores normalized audit reports. The 24 development packets cover Shopify, WooCommerce, Firebase, and generic web stacks. They are public regression material. Eight held-out slots are reserved for an independently arranged CTO/Opus review. Those slots have no packets, answers, or scores in this checkout.

Fixture checks establish packet structure, links between assertions and declared evidence, text line ranges, JSON pointers, and SHA-256 hashes. A validated fixture can support a supplied-evidence judgment run. Browser collection and its runtime measurements require an executed collection workflow. Any product scanner, real-world accuracy claim, release decision, and PR review require their own evidence.

## Run the fixture checks

Use Python 3.10 or later with the dependency in [requirements.txt](requirements.txt). The runner reads local files and writes machine JSON to stdout and a human summary to stderr. It makes no network calls, executes no fixture content, and runs no collection or model adapter.

```sh
python benchmark/runner.py > /tmp/dpdp-fixture-summary.json
```

A valid input run exits 0 by default, even with incomplete evidence. Invalid input exits 2. Add `--require-ready` when a blocked benchmark should exit 1. The default fixture-only run reports the outstanding evidence explicitly and returns no candidate accuracy metrics.

## Prepare blind inputs

The CTO arranges an independent Opus session with its own private workspace. Use the eight reserved IDs and stacks from [manifest.json](manifest.json). Put independently authored definitions and rubrics at `<private-held-out>/<case-id>/case.json` and the declared input artifacts beneath each case directory. The [schemas](schema/contracts.json) describe every field. Keep the held-out directory, rubric, raw runs, and judgment records in a private workspace outside every builder checkout. Keep the manifest slots pending in the public repository.

Each private definition pins an audit date, stack, mode, and scope. Use `input.scope` for precise scope and `input.artifacts` for the synthetic input paths. Use neutral filenames and neutral scope prose. The private `expected` object contains seeded findings and severities, sampled observations, required scope unknowns, forbidden claims, critical IDs, and remediation acceptance checks. Findings reference declared artifacts and can include optional `evidence_locations` per artifact. An optional `supporting_evidence` object maps exact assertion text to artifact locations. Use `L2`, `L2-L4`, or JSON pointers such as `/observations/0`. Use only synthetic data and reserved test domains in both cohorts.

The following commands run inside the independent workspace against a checkout of the reviewed runner. Set the private workspace variable and select the reserved ID for the candidate run.

```sh
private='/path/to/private-opus-workspace'
case_id='replace-with-reserved-case-id'

python benchmark/runner.py --held-out "$private/held-out" > "$private/fixture-summary.json"

python benchmark/runner.py \
  --held-out "$private/held-out" \
  --case-id "$case_id" \
  --export-inputs "$private/blind-inputs" \
  --export-alias-map "$private/blind-input-aliases.json"
```

Repeat `--case-id` to export multiple cases at once. The packet and alias map must use new paths outside the checkout. The exporter assigns a fresh opaque ID to each case and uses it as both the folder name and the `brief.json` ID. The brief includes stack, mode, audit date, scope, and artifact hashes. Declared files appear under `artifacts/`. The helper excludes the underlying case definition, title, expected fields, and fixture summary. Store the alias-to-case-ID map privately outside the candidate packet. The trusted normalizer uses it to restore the canonical case IDs for result paths and ledger records. The CTO checks that the chosen artifact names, content and scope prose preserve the blind boundary. Give candidates only their exported packets and a common audit prompt. Keep case definitions, fixture summaries, score reports, expected labels, review rubrics, and prior outputs away from candidate sessions. Development labels and fixtures are public, so development scores measure regression behavior. The export change applies to new packets. Existing frozen case definitions, hashes and already-neutral held-out exports can be retained.

## Record and compare runs

Store each candidate invocation in a separate run directory. Its name is the run ID and each case has a `<case-id>/result.json` relative to that directory. Retain the unedited candidate output beside the result and bind its exact bytes with `raw_report.path` and `raw_report.sha256`. The private fixture summary gives `case_sha256` to the trusted normalizer. The hash binds the case definition, including the rubric, and every declared input artifact. The exact pinned scope is repeated in the result. Record the actual timestamp, elapsed duration, tool versions, model identifier/version, and cost if measured. Use JSON `null` for missing values and include a currency code when recording cost. The runner separately reports its own elapsed time.

Candidates can write audit findings in free form. Opus reads the frozen report and privately maps its observations to the expected IDs and labels. A matched finding needs the reviewed severity and exact declared fixture references. Retain each unsupported reported finding as a distinct unmatched ID. Retain unexpected scope unknowns and sampled claims as distinct unmatched labels. Mapping preserves omissions, unsupported claims, severity differences, and evidence gaps. It evaluates the report as written and does not fill gaps from the rubric. The reviewer retains the mapping rationale and raw output locations in the private review record. Use `assessment.findings`, `assessment.unknowns`, and `assessment.sampled_checks` for the normalized claims. Use `findings`, `all_clear`, or `inconclusive` as the actual report verdict. Populate `remediation.items` only with actions actually proposed, with a linked finding ID and verification step.

The exact-ID comparison is a harness mechanism. Mapping that lacks an independently bound passing record is provisional. If either the normalized assessment or the judge-confirmed raw report asserts an all-clear despite seeded findings, expected unknowns, incomplete sampled checks, or incomplete collection, the summary counts a false all-clear. Correctly identifying a seeded scope unknown is desirable and rules out an all-clear for that case.

The programme calls for at least three fresh runs per hidden case per compared configuration. The runner's two-run minimum is only a structural check; it does not verify the programme's complete experiment design, independent invocations or matched model settings. Freeze and retain each raw output before normalization. The runner compares only cases with results in both runs and the exact same fixture hash. It reports pairing, missing results, finding precision and recall with counts, false positives, missed known gaps, critical misses, scope-unknown and sampled-check counts, and remediation coverage. Overall and per-stack summaries include stage coverage. Zero denominators are unmeasured. Scores on completed cases coexist with missing-result counts and a blocked gate.

### Optional collection adapter

A supplied-evidence run records collection as `pending` or `blocked`, with `origin: "none"`, an explicit reason, and no capture artifacts. Independent judgment and remediation readiness can be measured for these runs. Collection readiness remains pending.

A future Vettam or Playwright adapter can write `status: "captured"`, `origin: "adapter"` or `"browser"`, `reason: null`, and relative paths and SHA-256 hashes for nonempty capture artifacts from an actual synthetic execution. Record the collector name and version in result metadata. Preserve enough tool output for an independent reviewer to verify provenance and distinguish a new capture from supplied fixture evidence. The runner validates paths, bytes, and declared metadata. The operator verifies runtime provenance. The runner rejects capture records that reuse named fixture paths, fixture bytes, or the raw report as capture evidence.

### Independent CTO/Opus ledger

The CTO obtains actual review artifacts through the independently arranged Opus route. For each run and case, the private judge ledger binds `case_sha256`, `result_sha256`, and `raw_report_sha256`. Record the reviewer, precise model identifier as available, review timestamp, and durable `review_ref` to the review artifact. Its dimensions cover assessment mapping, expectations, legal accuracy, scope restraint, remediation, and collection provenance. Each dimension takes `pass`, `fail`, or `blocked` with a substantive rationale. The expectations dimension records review of the seeded rubric and its evidence, including difficulty and scope controls. Legal and restraint review considers dated applicability, unsupported claims, and incomplete evidence. Remediation review considers actionability, sequencing, verification, and the seeded criteria. Mark collection review blocked with the reason when the run used supplied evidence. This leaves independently reviewed judgment and remediation measurable on their own.

Each record also requires `raw_report_verdict` and `raw_report_verdict_confirmed`. The judge reads the frozen raw report and records its actual verdict as `all_clear`, `findings` or `inconclusive`, then marks confirmation true when the verdict can be confirmed from those bytes. Use false and record the reason in the assessment-mapping rationale if confirmation is unavailable. An unconfirmed verdict or disagreement with `assessment.verdict` blocks judgment readiness. Record the actual raw verdict even when it reveals an error in the normalized label. The runner compares structured fields and pinned bytes. The judge determines the meaning of the raw report.

Existing normalized results and frozen cases retain their format. For an older ledger, have the judge reopen each pinned raw report, add both required verdict fields, and have the operator repin the revised ledger. A provisional run without a ledger remains available.

The ledger envelope records who verified the provenance, when, and the `provenance_ref` for that verification. The CTO checks the independent reviewer identity and session, private ownership of the hidden packets and answers, raw run provenance, and binding to exact candidate output before supplying the digest through a trusted channel. The runner labels a supplied ledger “identity not verified by runner.” The checksum establishes agreement with the operator-provided bytes. The CTO verifies identity and provenance through the independent review protocol. Supply only the checked ledger and independently delivered SHA-256 digest to the runner. Until that evidence exists, omit the ledger and record the review as pending. PR review is a separate owner gate.

```sh
python benchmark/runner.py \
  --held-out "$private/held-out" \
  --results "$private/run-one" --results "$private/run-two" \
  --judge-ledger "$private/opus-judge-ledger.json" \
  --judge-ledger-sha256 "$verified_ledger_sha256" \
  --require-ready > "$private/paired-summary.json"
```

The overall gate stays blocked while held-out packets, repeated results, required collection, reviews, or any scoring blockers remain outstanding. A complete benchmark can become eligible for owner review. The machine summary always sets `release_claim_authorized` to false because the owner makes the release claim after reviewing the evidence.
