---
name: india-dpdp-audit
description: Audit websites and repositories for Indian DPDP privacy compliance and readiness using current official law, visible user journeys, and available implementation evidence. Use for requested Indian data-protection audits, not general code reviews or compliance certification.
---

# India DPDP audit

Last verified: 2026-10-27 (Gazette texts, the PIB release and all links in the legal reference). Review cadence: re-verify before each regulatory date (Consent Manager phase and full enforcement). 13 November 2026 and 13 May 2027 are conservative working preparation dates derived from the printed Gazette date (13 November 2025); the legal trigger is the period from publication, and the exact calendar day is unresolved until verified and on any MeitY notice.

Produce a proportionate, evidence-based audit. Separate law currently in force, future obligations, good practice, and facts that need internal verification.

## Establish scope and current law

1. Record audit date, target domains, any authorised repo/commit, and scope (public website, code, or internal controls). Use supplied information before asking questions. Public-only work may proceed while internal facts remain unknown.
2. If supplied a PDF, identify its title, Gazette number, date and whether it is an Act, draft, final rules, notification or commentary. Read relevant provisions and inspect pages where extraction is uncertain. A 2023 Act PDF is not a complete current legal baseline.
3. Read [the legal reference](references/legal-baseline.md). Browse official MeitY, e-Gazette, India Code and relevant regulator sources for current texts, commencement, amendments, corrigenda, exemptions and applicable orders. Use commentary only to locate primary evidence. Record unresolved changes rather than silently assuming an old text is current.
4. Build a small legal ledger: instrument/provision, publication date, effective date, status on audit date, official URL and access date. Distinguish Gazette publication from website upload. Where sources disagree, record the discrepancy and conservative preparation date; do not resolve legal ambiguity by guesswork.
5. Assess applicability: entity and Indian nexus, personal-data flows, fiduciary versus processor, children, lawful guardians, and notified Significant Data Fiduciary status. Business contact details can still identify individuals. Public accessibility alone does not establish the Act's public-data exclusion. Do not assume a startup exemption; section 17(3) applies only to classes the Central Government notifies.
6. Check existing IT Act/SPDI and sectoral obligations separately where relevant. Deferred DPDP duties do not imply that privacy law is absent today. SPDI Rules under IT Act s.43A apply until DPDP s.44(2) commences. Avoid expanding into an unrelated full legal audit.

## Gather evidence safely

- Follow visible navigation from the homepage to contact, booking, newsletter, careers, account, payment and privacy pages, as available. For a brief audit sample representative journeys and state coverage; do not crawl indefinitely.
- Record exact URL, observation date, fields, required/optional status, purpose explanation, nearby notice, links, consent choices and available withdrawal/grievance routes. Preserve small relevant excerpts or screenshots, not unnecessary personal data.
- Inspect public browser behaviour or source for third-party scripts, embeds, cookies and storage when available. Separate a script reference from an actual network transfer; a `mailto:` or external link is not an embedded tracker. Record what happens before consent and after rejection only if actually observed.
- Search results and text extraction can omit dynamic forms and footers. Confirm an apparent missing policy or broken route in a rendered browser where possible. Otherwise say “not located in the inspected pages,” not “does not exist.”
- Remain read-only. Do not submit forms, send messages, create accounts, upload files, buy anything, access other people's data, or run vulnerability scans without specific authorisation. Ordinary navigation is allowed. Do not fix or deploy changes during an audit unless requested.
- If code access is authorised, follow repo instructions and trace sampled flows from UI through API, database, processors and deletion. Cite file/line and commit. Do not infer deployed behaviour from source without deployment evidence. Do not copy secrets or production records.

## Evaluate controls

For each processing purpose identify the claimed lawful ground. Distinguish consent under section 6 from an applicable specific use under section 7; do not import GDPR's general “legitimate interests” test. A voluntarily submitted enquiry may support the requested response, not unrelated marketing.

Check these areas as applicable:

| Area | Public evidence | Internal evidence needed |
|---|---|---|
| Notice and consent | Understandable itemised data/purpose notice, meaningful affirmative choice where consent is used, accessible language and rights links | Notice version and consent evidence, purpose separation |
| Minimisation and purpose | Necessary fields, optional fields, no bundled unrelated marketing | Data inventory, downstream reuse, access and sharing |
| Rights and contact | Authorised privacy contact; withdrawal, access, correction, erasure, grievance and nomination routes as applicable | Identity checks, response handling, processor propagation and completion records |
| Retention | Accurate stated retention criteria | Purpose-specific schedules, legal holds, deletion jobs, backups; applicable rule-specific retention |
| Processors and transfers | Relevant vendors/embeds and accurate explanations | Contracts, sub-processors, actual destinations and applicable transfer restrictions |
| Security and incidents | HTTPS and directly observable exposure only | Access controls, safeguards, logging, recovery, breach notification playbook and exercises |
| Children/guardians | Audience and age/guardian journey if relevant | Verifiable consent and applicable exemptions; no assumption all sites must collect identity documents |
| Conditional duties | Evidence of SDF or Consent Manager status | Notification, statutory officer/auditor/DPIA duties where triggered |

Do not prescribe a cookie banner solely because cookies exist. Assess whether personal data is processed and the applicable ground. Do not demand a statutory DPO or registered Consent Manager for every business, blanket India-only storage, or an independent consent checkbox for every form. Recommend controls proportionate to actual processing.

Read the actual breach rules before citing deadlines: distinguish prompt initial notifications from subsequent detailed reporting; do not describe “72 hours” as a universal permission to delay. Distinguish any CERT-In duty and its separate trigger/deadline.

## Delegation and synthesis

When delegation is authorised, use independent solo reviewers with narrow tasks, for example public notices/rights and forms/third-party processing. Give each this skill and the same audit date and scope. No recursive delegation or concurrent control of one browser tab. Each returns evidence, legal basis/status, uncertainties and suggested remedy. The primary agent verifies and deduplicates findings.

## Report

Lead with a bounded conclusion: observed readiness/current-law concerns and what cannot be established. Never certify compliance from a public scan or report an uncommenced obligation as a current violation. An audit that finds a Consent Manager or other phase item must state the date uncertainty and never call it a current violation before the phase has commenced on every reading. State that the report is a technical and readiness review, not legal advice, and that applicability, exemptions and deadlines should be confirmed with qualified Indian counsel.

For each finding record: priority, observation and URL or file/line, applicable provision and official source, effective status, confidence, practical fix, and a verification step. Use these evidence labels:

- **Observed gap**: evidence demonstrates a missing control; specify whether the duty is currently applicable or still a readiness requirement.
- **Not verified**: unavailable backend, contract, deployment or operational evidence; absence of public proof is not proof of noncompliance.
- **Meets sampled check**: narrow observed success, never blanket compliance.
- **Not applicable**: give the evidence supporting exclusion; otherwise applicability is unknown.

End with a short prioritised action list and the few internal questions that materially change the result. Clearly distinguish legal requirements, interpretation, and optional good practice. Cite authoritative sources alongside legal claims and keep the report brief when requested.
