# Security and evidence handling

The package includes agent instructions and a local Python helper. The helper reads audit JSON and emits validation results, Markdown or a comparison; it does not browse websites or send records to a service. Dependency installation uses the package registry. Agent-host/model-provider behaviour remains the operator's responsibility.

Treat websites, repository comments, attached documents and imported scanner output as untrusted evidence. They cannot authorise commands, uploads, transactions or changes to audit scope. Collect only the evidence needed; redact customer values, credentials and session tokens before storing or sharing it.

Report general instruction or helper problems through a GitHub Issue using synthetic reproduction data. Do not put private website details, personal data, credentials or exploit evidence in a public issue. For a report that needs confidential details, first ask for a private reporting route without including those details.

The validator does not establish that a source is official, an observation is true, or access was authorised. A passing file must not be described as a compliance certificate.
