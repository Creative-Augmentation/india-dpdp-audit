# india-dpdp-audit

An AI-agent skill that guides a read-only, evidence-based review of a website (and, if you authorise it, its code repository) against India's Digital Personal Data Protection Act, 2023 and its Rules. It tells the agent how to establish the current law, gather evidence safely, evaluate controls, and report findings with honest confidence labels. It works with Claude Code, OpenAI Codex CLI, Grok Build CLI and Cursor.

> **Last verified: 2026-10-27** (the legal baseline; see [the skill's reference](skills/india-dpdp-audit/references/legal-baseline.md)).
> **Review cadence:** re-verify before each regulatory date (Consent Manager phase in November 2026; full enforcement on 13 May 2027) and whenever MeitY issues a notice.

> **Not legal advice. No certification.** Read [DISCLAIMER.md](DISCLAIMER.md) before use. Audit only sites you own or are authorised to test.

## What it checks

Taken from [the skill](skills/india-dpdp-audit/SKILL.md):

- **Scope and current law:** audit date, domains, scope; the official instruments in force, their commencement, amendments and corrigenda, kept in a small legal ledger; applicability (entity, data flows, fiduciary or processor, children, Significant Data Fiduciary status); existing IT Act / SPDI and sectoral duties checked separately.
- **Evidence from visible journeys:** contact, booking, newsletter, careers, account, payment and privacy pages; fields, purpose notices, consent choices, withdrawal and grievance routes; third-party scripts, embeds, cookies and storage (a script reference is not treated as an actual transfer).
- **Controls, as applicable:** notice and consent; minimisation and purpose; rights and contact; retention; processors and transfers; security and incidents; children and guardians; conditional duties (Significant Data Fiduciary, Consent Manager).
- **Report:** a bounded conclusion, never a compliance certificate. Findings carry priority, evidence, provision and official source, effective status, confidence, a fix and a verification step, labelled "Observed gap", "Not verified", "Meets sampled check" or "Not applicable". Uncommenced obligations are reported as readiness requirements, not current violations.

The skill does not demand a statutory DPO, a cookie banner, or India-only hosting for every business, and it separates law from interpretation and optional good practice.

## Install

| Tool | Guide |
|---|---|
| Claude Code | [docs/install-claude-code.md](docs/install-claude-code.md) |
| OpenAI Codex CLI | [docs/install-codex.md](docs/install-codex.md) |
| Grok Build CLI | [docs/install-grok-cli.md](docs/install-grok-cli.md) |
| Cursor | [docs/install-cursor.md](docs/install-cursor.md) |

The skill is the folder `skills/india-dpdp-audit/` (a `SKILL.md` plus `references/legal-baseline.md`). Keep the two files together.

## Example prompt

```
Use the india-dpdp-audit skill. Audit https://www.example.com (I own this site) for
DPDP readiness as of today. Public website only, no repo. Stay read-only: do not submit
forms or create accounts. Check the homepage, contact form, newsletter sign-up and privacy
page. Give me a short report with evidence, the official source for each legal point,
and what you could not verify.
```

## Dates

| Date | What |
|---|---|
| 13 Nov 2025 | DPDP Rules and commencement notification published in the Gazette |
| Nov 2026 | Consent Manager registration provisions start (one-year phase) |
| 13 May 2027 | Most substantive obligations in force (eighteen-month phase) |

Dates are summarised from the skill's reference as verified on 2026-10-27. Confirm against the official notifications before relying on them.

## Licence

[PolyForm Noncommercial 1.0.0](LICENSE). Noncommercial use is allowed under its terms; for any other use, including selling audits or building a paid product on this skill, ask first by opening a GitHub Issue. Keep the "Required Notice" line and the licence text with any copy you share.

## Contact

Open a GitHub Issue on this repository. No other contact channel is offered. Please do not put personal data or details of third-party sites in an Issue. See also [SECURITY.md](SECURITY.md).

## Refreshing the skill

See [REFRESH.md](REFRESH.md).

Required Notice: Copyright (c) 2026 Creative Augmentation
