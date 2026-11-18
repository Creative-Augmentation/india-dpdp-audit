# Contributing

Use a feature branch and a pull request. Preserve the read-only audit default and support brief human-readable reviews as well as structured handoffs.

- Keep shared behaviour in `SKILL.md`; put platform-specific details in the relevant playbook.
- Cite official legal and vendor sources, record the access date, and label interpretation and applicability. Never copy another project's legal conclusions without checking the primary instrument.
- For schema or helper changes, include a synthetic example and tests of the affected behaviour. Install `skills/india-dpdp-audit/scripts/requirements.txt` and run `python -m unittest discover -s tests -v`.
- Use `evals/` for realistic agent cases. Keep input and expected results separate and use the blind protocol. Do not claim evaluation success unless the recorded run actually occurred.
- Use `benchmark/` for the Phase 1 synthetic regression set and offline scoring. Keep private held-out packets and judge ledgers outside the checkout. Public expected answers are never evidence of independent accuracy. Opus review and judging are required for this programme; builder tests do not substitute for them.
- Keep customer reports, credentials and identifiable records out of commits, issues and CI. All committed examples must be invented.
- Record external code or dataset reuse and its exact licence before importing it. The current release contains original implementation; research links do not imply bundled dependencies or endorsement.

A validator can enforce structure and consistency; reviewers must still assess evidence relevance, legal interpretation and whether a proposed fix solves the actual problem.
