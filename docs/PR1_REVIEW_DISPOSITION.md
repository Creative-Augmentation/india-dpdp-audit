# PR #1 review disposition — 18 November 2026

The independent Opus review evaluated `a3f115ee78e38f71ad4d76f16ad708b67ab1b1f2`, with 6 must-fix, 14 cheap and 6 later findings. Its verdict was foundation approval only after must-fixes; it did not approve a merchant launch. This document records builder responses. **It is not reviewer sign-off on the changed head.** Keep the PR draft pending follow-up Opus review and CI.

| Review ID | Builder response and remaining limit |
|---|---|
| 1 — must-fix | Gap-first summary, explicit could-not-check counts and coverage, disclaimer, evidence-status-first ordering and caveated empty findings. Empty coverage and blocked-only records have regression coverage |
| 2 — must-fix | Sampled passes and exclusions reject asserted/limited evidence padding; all linked items must be direct and within the audit window. Semantic relevance still needs independent review |
| 3 — must-fix | Audit window defaults to the audit day. Diff warns on unsupported status upgrades and removed gaps. Fresh evidence must have a new ID and a later India calendar date to suppress the upgrade warning; removal never proves closure |
| 4 — must-fix | Pinned Act/Rules phase registry checks recognized citations and bounded 13/14 dates; stale future entries are rejected. Mixed or unmapped DPDP citations cannot silently receive a definitive phase. Corrected the current-duty test fixture. This is dated consistency checking, not automatic legal research |
| 5 | Missing date/date-time checkers fail with dependency guidance; naive timestamps rejected without timezone-dependent interpretation |
| 6 | UTF-8 BOM accepted; JSON and diff input failures identify their path |
| 7 | Ordinary punctuation, Indic combining marks and joiners preserved; dangerous markup and links escaped; injection regressions retained |
| 8 — later | Defined directly inspected internal artifacts versus owner assertions. Automated semantic provenance verification and a new record-type schema remain deferred; relabelling a claim is not a legitimate pass |
| 9 | Added section 5(3), section 9(3), Rule 15 and Rule 14(3) checks. Primary Rule 14(3) concerns grievances; no blanket ninety-day promise for every rights request |
| 10 | Re-fetched October order and May PIB statement. January upload is draft-consultation feedback, not consolidated Rules. Alternate official 2011 PIB page retrieved; old MeitY SPDI route returned 404, so government Gazette fallback remains explicit |
| 11 | Ticket retention/deletion example now links to future statutory retention/erasure duties, retaining applicability uncertainty |
| 12 — later | Uses section 7's “certain legitimate uses” terminology and retains the warning against importing GDPR legitimate interests |
| 13 | Added merchant-facing Shopify settings, evidence, limits and request-route table; checked current primary Shopify guidance |
| 14 — later | Added distinct phone/OTP checkout, WhatsApp/COD and other app flow checks when present; actual provider-specific implementations remain Phase 3 work |
| 15 — must-fix | Audited repository instructions and scripts explicitly untrusted; install/build/test execution requires separate authority and isolation |
| 16 | Added raw page, repository-agent-file, scanner verdict and owner-document injection packets with structured-record rubrics; these new model evaluations are prepared, not executed |
| 17 | Added entirely blocked-access case plus owner compliance assertion; requires could-not-check result and evidence requests |
| 18 — later | Summary implemented. Merchant one-command collection remains Phase 2, clearly labelled as unavailable; host discovery tests and final merchant onboarding remain open |
| 19 — must-fix / owner gate | README now explicitly says for-profit self-audit requires permission under the current licence. Custom self-use terms are drafted, not adopted. Merchant campaign remains blocked until owner-approved adoption updates both licences and descriptions |
| 20 — later | Added primary-source component compatibility assessment. No Vettam implementation, data or rationale imported. CC BY-ND permits private adaptations but does not grant sharing adaptations; no blanket claim that it forbids every modification |
| 21 | Configured this checkout's future commits with the account's GitHub noreply address. Existing public commits were not rewritten. Maintainer must check squash author/committer identity before any approved merge |
| 22 | Removed credential/process details from public CI note; pinned action revisions and added benchmark/hygiene checks. Local supported-version tests are separate from still-pending hosted CI activation |
| 23 | Install guide limitations rewritten neutrally. Runtime discovery in each host remains unverified; no installation claims were manufactured |
| 24 | Fixed disclaimer reference, marked prepared evaluation sets unrun, and identified the exploratory model by its actual name |
| 25 | Added bounded public-fixture hygiene checker with redacted diagnostics. Heuristic numeric/domain checks are not proof of anonymisation. Scanning arbitrary private audit records for personal data is deferred; existing minimisation instructions remain mandatory |
| 26 — later | Diff warns about changed subject/domains and ignores ID-list reorderings. Human-readable diff mode and broader source-host warnings remain deferred; official sources still require human/agent verification |

## Validation and follow-up

Regression coverage includes evidence padding, audit windows, false all-clears, phase contradictions, missing format dependencies, Unicode/injection boundaries, diff closure and scope changes, benchmark provenance and fixture hygiene. All **70 tests passed on Python 3.10.19 and 3.14.7** locally. The copied skill validated/rendered outside the repository on both versions, and metadata, relative links and whitespace checks passed. All 24 benchmark packets validated, and the gate correctly remained blocked. The five local browser-fixture checks passed on Chrome 157.0.8103.79. The build handoff records the final commit and retained logs; hosted CI remains pending.

Opus should rerun the original probes against the updated head, inspect the changed evidence and phase boundaries, and review the new benchmark normalisation/provenance design. The old review's passing 22-test result applies only to its old head. Hidden packets, repeated candidate baselines and Opus judging remain outstanding; neither this disposition nor passing unit tests establishes that our results exceed Vettam's.
