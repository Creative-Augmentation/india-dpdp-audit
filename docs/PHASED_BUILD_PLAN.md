# DPDP audit delivery plan

Recorded 18 November 2026. The owner approved **Phases 0 and 1**: foundation and benchmark. Later phases are the planned route, not a current instruction to release, deploy or scan third-party systems. The initial feature work remains in [draft PR #1](https://github.com/Creative-Augmentation/india-dpdp-audit/pull/1).

The product goal is a merchant-run tool that identifies evidenced gaps in Shopify, WooCommerce, Firebase and other websites, then produces a practical fix plan. The intended entry point is one command and a gap-first summary readable in about two minutes. A hosted free scan is a later distribution option. The present Python helper formats supplied records; it does not yet implement that merchant scanner.

## Phase sequence and completion gates

| Phase | Work and deliverable | Gate |
|---|---|---|
| **0 — approved** | Stabilise the evidence/remediation contract; gap-first report; portable package; custom licence proposal; independent review of PR #1; CI | Opus review resolved on the actual PR head; supported-version checks and package checks pass; CI active. Licence adoption requires separate owner approval |
| **1 — approved** | 24 public synthetic development packets, eight independently authored private cases, offline scoring and local browser fixtures; pinned competitor baselines | Opus reviews expectations, freezes hidden inputs and judges repeated matched runs; report collection, judgment and remediation separately with counts and limitations |
| 2 — next priority | Merchant command, authorised evidence collection, replaceable collector interface; evaluate pinned Vettam against original fixtures and fill measured gaps | Actual capture of rendered forms/notices, requests/storage, initial/accept/reject/withdraw/revisit; correct scope, isolation, redaction, failure reporting and provenance |
| 3 | Executable platform checks, in order: Shopify, WooCommerce, Firebase, generic; allow mixed stacks | Every advertised check has a positive, negative and insufficient-evidence case plus an implementable fix and retest |
| 4 | Remediation lifecycle: proposed, implemented, verified, still failing, blocked; new evidence required for closure | Complete fixes pass; seeded partial fixes cannot close; schema migration and dependencies documented |
| 5 | Authorised pilots, one test environment per stack; matched full-pipeline comparison and release preparation | Independent review, measured support matrix, unresolved limitations disclosed and owner release approval |

Phase 2 is the product's critical path. Phases 0 and 1 exist to prevent an unreliable scanner and unmeasurable claims. Do not expand them into a hosted product or a general compliance platform.

## Measurement rules

- Separate collector measurements from judgment on identical supplied evidence and from remediation quality. A packet reader is not a browser collector; a unit-test pass is not an accuracy result.
- Freeze revisions, allowed inputs, prompts, case hashes, tool/model settings, raw outputs and run identifiers. Record actual time and available usage; use unknown for unreported cost or tokens.
- Candidate agents see neutral input briefs and artifacts, not answer keys or expected finding identifiers. Independent judging maps frozen candidate output to the expected outcomes. Keep all hidden packets and judge records outside builder checkouts.
- Use two hidden cases per stack. Run each hidden case at least three times per compared configuration, with fresh sessions. Report variability, per-stack counts and every critical miss. Reuse of exposed cases cannot support a fresh independent claim.
- Programme targets are precision at least 95%, recall at least 90%, every seeded critical detected, zero unsupported current-law violations, zero false verified closures and zero false all-clears. Report numerators and denominators, including undefined values, rather than only percentages. These are targets, not measured performance.
- A finding requires evidence and a legal or good-practice basis; an observed gap needs a target, responsible role and acceptance test. An unverified control needs an evidence request. Missing evidence must remain visible as “could not check”.

The four-case exploratory comparison from the initial build produced equal 24/24 scores on its narrow rubric using the same supplied evidence and Vettam outputs. It was builder-authored, one run per skill, and judged by Terra. It establishes neither independent collection accuracy nor superiority. It does not satisfy the new Opus benchmark gate.

## Execution and authority

Sol agents implement bounded components in separately owned files. The coordinating Mac session integrates and tests them. The CTO arranges an independent Opus review of the PR and Opus judging of hidden benchmark runs; same-model builder review does not replace that gate. Review records must identify the reviewed commit, actual model/session and input/output hashes, with operator verification of provenance.

The approved [licence direction](licensing/CUSTOM_SELF_USE_LICENSE_DRAFT.md) is free self-audit for any business, with agency services and resale reserved. The proposal is not active. Keep the existing root and packaged licences until the owner approves exact replacement text. Check [upstream component terms](licensing/UPSTREAM_COMPATIBILITY.md) before importing code, data or rationale. External lawyer review before a campaign is not a project gate; uncertainty and disclaimers remain explicit.

Customer audits require the owner's authority over the target and the allowed interactions. Campaign contacts need their applicable lawful basis and an unsubscribe path. Do not initiate unsolicited scans of prospects. Main merges, releases, paid infrastructure and production-changing actions are outside this Phase 0/1 execution approval.

## Present limitations and next handoff

The foundation has no automated collector. The [benchmark packets](benchmark-coverage.md) are synthetic; an independent Opus author has frozen eight private cases, while candidate runs and judged results remain pending. Local tests and the [CI template](../ci/README.md) are separate evidence. Hosted CI still needs a maintainer with workflow permission. Opus has reviewed earlier heads; changes after those reviews require follow-up review of the actual new head.

Close Phase 0 only after its independent review and CI gates pass. Close Phase 1 only after independent hidden-case preparation and actual baseline runs are recorded. Until then, describe this work as implemented scaffolding with pending validation, and keep PR #1 draft.
