# Audit and remediation foundation

Version 0.2.0 implements a portable audit contract, local validation/rendering/comparison, platform playbooks and synthetic evaluations. The AI agent remains responsible for authorised evidence collection and interpretation. No external scanner is a runtime dependency.

## Research decisions

Public sources reviewed on 18 November 2026. The following are design references, not imported code or legal authorities.

| Reference | Reviewed revision | Pattern retained | Boundary |
|---|---|---|---|
| [Vettam scanner](https://github.com/Vettam/dpdp-compliance-scanner/tree/d135d85d47c84486ad39032c88e0a696178bdcf7) | d135d85 | Separate observations, human assertions and findings; stable records across audits | Code Apache-2.0, vendor data CC BY-SA 4.0, legal rationale CC BY-ND 4.0; no code, data or rationale copied |
| [Vigil](https://github.com/prathikcannotcode/Vigil/tree/0641b662c39c0f063246f932bb27a87e4af02ef6) | 0641b66 | Structured findings, ownership, verification and blind synthetic examples | Apache-2.0; workflow inspiration, no imported implementation or penalty model |
| [truScanner](https://github.com/truconsent/truscanner/tree/6729d6e0f4633c595858b00d58421348619a14e2) | 6729d6e | Optional source-discovery input | MIT; raw matched values need minimisation before ingestion |
| [DPDP Self-Check](https://github.com/sahilsinghi/dpdp-compliance-tool/tree/c7f877f363016f1c8e2dcedd0cfb98a6394d5b7f) | c7f877f | Owner questionnaire and report handoff | MIT; no copied legal baseline or numerical compliance score |
| [ShipSafe India](https://github.com/abdash1994/shipsafe-india/tree/cdab8dd8212ca6e0fe0aefd97bfd671da23c132f) | cdab8dd | Make blocked and manual checks visible | BSL competing-product restriction; no implementation or text imported |

The repository's PolyForm Noncommercial licence is unchanged. An upstream project's public visibility does not establish permission to relicense its components.

## Next collector experiment

Evaluate a pinned Vettam collector on synthetic local sites behind an adapter to this package's evidence format. Do not accept upstream findings as authoritative legal verdicts. Compare captured facts, skipped interactions, redaction, state isolation and date metadata against a small known-answer benchmark before adopting a dependency.

A useful candidate must retain failed/blocked visits, distinguish script references from requests, record whether an interaction actually happened, and prevent stale observations from silently closing findings. Tests should include initial load, acceptance, rejection, withdrawal and revisit. The current release does not claim this collector experiment or a real browser audit has passed.

Platform-specific remediation remains owned here. Public observations, repository review, internal records and synthetic staging tests have different scopes; an adapter must not promote one into another. Backend coverage remains unknown until suitable evidence is supplied.
