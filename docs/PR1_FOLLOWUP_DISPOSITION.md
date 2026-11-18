# PR #1 Opus follow-up disposition — 18 November 2026

The independent follow-up reviewed `ab00e090663766e8cbc4445988f7e3bcab52d17f` using `claude-opus-5-5`, high effort. It verified four earlier must-fixes for the foundation PR and identified one remaining blocker, nine cheap items and seven later items. The reviewer ran all 70 tests on Python 3.13.5 at that head. This document records builder changes after that review; **the new head needs independent review**.

| Follow-up item | Response |
|---|---|
| Must-fix 1 — legal aliases skip phase checks | Added DPDPA/DPDPR, Act number, full/short title, Hindi and Rules-of aliases, and operative baseline URL coverage. Opaque official citations now require instrument identification or uncertainty; explicitly identified non-DPDP laws keep generic checks. A DPDP name or pinned source cannot be hidden behind an unrelated law label. Future ledger entries require an effective/preparation date |
| Cheap 1 — wide stale audit window | More than 31 inclusive days requires an explicit reason. Summary shows the window, oldest linked evidence and extended-window warning. Historical gaps remain dated pending retest; wide-window passes are visible and do not establish fresh closure |
| Cheap 2 — GFM autolinks | Link-shaped untrusted text renders in dynamically fenced literal code spans. Tests use the pinned real GFM renderer, covering email, mailto, xmpp, ftp, www, HTTP(S), hostile markup/backticks and Indic joiners |
| Cheap 3 — hint-bearing export IDs | New blind exports use random opaque aliases; the canonical map is a separate private file outside the candidate packet. Existing frozen neutral held-out exports are not modified |
| Cheap 4 — indefinite timing uncertainty | A single mapped phase retained as uncertain after its latest commencement requires an explanatory note and produces a warning; note truth and authority still require review |
| Cheap 5 — preloaded host configuration | Skill and installation guides require a separate trusted workspace, read-only target outside the project root, declined folder trust and no target hooks/settings/MCP activation |
| Cheap 6 — inbound contribution rights | Added explicit permission gate before merging outside contributions during the licence transition. No automatic assignment or retrospective relicensing grant is claimed; exact replacement licence still awaits owner approval |
| Cheap 7 — older commit email | Current commits use noreply. The older published commit is unchanged; maintainer must select noreply squash identity before an approved merge. No history rewrite or merge was performed |
| Cheap 8 — raw verdict hidden by normalisation | Judge ledger now requires the raw verdict and confirmation. Disagreement or unconfirmed verdict blocks judgment; a confirmed raw false all-clear remains counted. The runner explicitly says reviewer identity is not verified by it |
| Cheap 9 — weak tests | Added real GFM output assertions, true non-DPDP positive controls and alias/opaque-source negative tests, plus positive judge-ledger acceptance and identity-disclaimer tests |
| Later 1 — unrelated direct evidence | Still open. Journey-linked findings and semantic relevance require further contract design and independent evidence review; direct/fresh labels alone do not prove relevance |
| Later 2 — copied “new” evidence | Diff warns when a new ID/timestamp repeats the earlier kind, locator and observation. It no longer treats that copy alone as fresh closure evidence; this is a comparison heuristic, not authenticity verification |
| Later 3 — self-declared judge identity | Remains an external provenance gate, now explicit in machine and human output. A pinned hash authenticates neither the model nor the author |
| Later 4 — ZIP boundary | No-Git fallback now protects the repository root, not just `benchmark/`; regression rejects a ledger placed at the ZIP root |
| Later 5 — bounded preview / grammar | Singular “1 recorded check” fixed. Preview remains bounded for readability with omitted counts and full detailed coverage; no claim of exhaustive summary text |
| Later 6 — support-firm permission | Owner decision remains pending. The unchanged draft permits only individual contractors for limited internal support; a separate IT firm would need additional permission. Do not treat approval of a general licence direction as approval of this detail |
| Later 7 — hosted CI | Still pending activation by a maintainer with workflow permission. Added test-only renderer installation to the pinned template; local tests are separate evidence |

## Frozen hidden set and next run

The independent Opus author recorded eight private cases, two per stack, with a 35-file manifest. The coordinator verified the manifest and file hashes without opening hidden answers. Public case definitions are unchanged; new result-ledger fields and export alias handling are documented in [the benchmark protocol](../benchmark/README.md). The old frozen packets are not automatically re-authored when the runner changes.

No candidate score is claimed by this follow-up. Before candidate execution, freeze the evaluated head and matched configurations, keep the rubric outside every candidate session, and record three fresh runs per case/configuration. Opus must judge the frozen raw outputs and confirm their actual verdicts. Report-only tests and native collector comparisons must remain separately labelled; a Vettam skill deprived of the CLI outputs it requires is not a valid native Vettam benchmark.

Local validation: **87 tests passed on Python 3.10.19 and 3.14.7**, including actual GFM rendering. Copied-package validate/render passed outside the repository on both versions. Skill metadata, relative links, public fixture hygiene, 24 public benchmark packets and whitespace checks passed. These checks are separate from hosted CI and independent review of the changed head.

The current PolyForm licence and custom draft remain unchanged. This work authorises no launch, main merge, claim of superiority or licence replacement. Refer to the CTO handoff for final commit, validation logs, the private frozen-set hash and follow-up actions.
