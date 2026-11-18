# Remediation plan (human-readable planning view)

The JSON output contract, when used, is canonical. Describe proposed work; do not imply it has been implemented or deployed.

| Action ID | Finding IDs | Kind | Priority | Verification status |
|---|---|---|---|---|
| | | remediation / evidence_request | | pending |

For each action, record:

- Evidence status, applicability and legal status of the linked findings:
- Summary and concrete target (platform setting, code location or stated unknown):
- Responsible role:
- Effort estimate and assumptions, or what must be learned to estimate it:
- Dependencies by action ID and material unknowns:
- Acceptance criteria:
- Verification mode (public, repository, internal or staging) and steps:
- Verification evidence IDs, when available:

Use unique IDs and link actions to findings. The contract distinguishes action kind `remediation` or `evidence_request` and verification status `pending`, `blocked`, or `verified`. State which checks require owner authorization or synthetic staging. Record legal holds, vendor propagation and applicable exceptions. Mark verification complete only after evidence of the scoped retest; deployment and operational results need separate proof.
