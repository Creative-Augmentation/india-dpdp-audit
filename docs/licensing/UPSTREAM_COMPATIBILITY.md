# Licence compatibility and import boundary

Reviewed 18 November 2026. This is an engineering licensing assessment, not a legal opinion. The custom self-use terms are [a proposal](CUSTOM_SELF_USE_LICENSE_DRAFT.md); the root and packaged PolyForm licences remain operative. No Vettam code, vendor data or explanatory prose has been copied into this project. Running a separately obtained upstream checkout for comparison is not a decision to bundle it.

## Pinned upstream inventory

Vettam `dpdp-compliance-scanner` version 2.1.0, revision `d135d85d47c84486ad39032c88e0a696178bdcf7`, identifies four licensing categories in its [NOTICE](https://github.com/Vettam/dpdp-compliance-scanner/blob/d135d85d47c84486ad39032c88e0a696178bdcf7/NOTICE). The package's top-level `license` field is not a complete inventory.

| Component | Upstream terms | Integration decision |
|---|---|---|
| Scanner code | Apache-2.0 | Candidate for a separate pinned collector or adapter; preserve upstream rights, licence, attribution and applicable NOTICE; mark modifications |
| Tracker/vendor data | CC BY-SA 4.0, per upstream notice and component labels | Keep separately identified; do not put the custom agency restriction on this dataset or an adaptation |
| `rationale_plain`, `rationale_dev`, explainer pages | CC BY-ND 4.0 | Exclude copied or adapted prose from our report templates and rule explanations; write our own analysis using primary legal sources |
| DB-IP Lite geolocation | CC BY 4.0 | Avoid importing unless needed; preserve attribution and identify provenance/version if included |

The repository's historical paths and component notices must be reconciled against the exact files in any chosen built package. This table is not an exhaustive dependency inventory or approval to import a distribution.

## What the source terms imply

Apache-2.0 section 4 permits additional terms for our modifications or a derivative as a whole while requiring preservation of the upstream licence, relevant notices and modification notices. Inference: original wrapper code can use our terms, but we cannot promise exclusive control of independently available Apache code. Preserve a clear component boundary. [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)

CC BY-SA 4.0 requires attribution and, when sharing adapted material, an allowed share-alike licence. It bars downstream restrictions on licensed rights and also addresses database rights. Inference: our agency restriction must not be presented as a restriction on the dataset or its adaptation. A collection and an adaptation are distinct questions; separation alone does not decide every case. [CC BY-SA 4.0, sections 2–4](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en)

CC BY-ND 4.0 allows sharing unadapted licensed material under its conditions; it does not grant permission to share adaptations. Inference: translating or rewriting copied upstream rationale into a distributed report can create a rights question. Use original explanations derived independently from official instruments, or obtain separate permission before redistributing adapted upstream text. [CC BY-ND 4.0, sections 2–3](https://creativecommons.org/licenses/by-nd/4.0/legalcode.en)

The proposed restrictions on agency services and resale mean the custom licence should be described as source-available, not OSI-approved open source. This follows the Open Source Definition's redistribution and field-of-use requirements. [Open Source Definition, sections 1 and 6](https://opensource.org/osd)

## Before any import

1. Pin the upstream revision and built-package checksum; list every copied file and its component licence, including generated output and runtime dependencies.
2. Decide whether the integration collects observations only or also emits upstream datasets and rationale. Keep findings from other tools labelled as external assertions, not our legal conclusions.
3. Preserve applicable licences, notices, attribution, modifications and provenance. Add an explicit third-party manifest with path boundaries; test packaged outputs as well as source files.
4. Check vendor data and any report excerpts against their own conditions. Do not assume “JSON output” or “optional dependency” removes redistribution obligations.
5. Keep our independently authored rules and explanations traceable to primary law, with dates and uncertainties. Do not copy upstream wording merely to replace its labels.

Phase 2 should evaluate the collector on synthetic local sites before choosing an import. A compatibility decision for one component does not approve the entire npm package, dataset, rationale or trademarks. If a necessary component conflicts with the intended distribution, omit it, implement an original alternative, or obtain separate permission.
