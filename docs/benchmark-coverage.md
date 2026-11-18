# DPDP benchmark coverage

The development set contains **24 synthetic cases**, six per stack. It supplies 48 local input artifacts, 11 expected technical findings and three seeded critical findings. Thirteen cases contain no expected technical finding. Those cases still test bounded observations, unavailable evidence or legal classification. The fixture audit date is 18 November 2026.

| Stack | Development cases and sampled coverage |
| --- | --- |
| Shopify | `sh01` initial and revisit theme analytics, `sh02` successful choice cycle, `sh03` app webhook delivery versus erasure completion, `sh04` merchant routing and scoped webhook applicability, `sh05` review widget interference, `sh06` unavailable region and runtime evidence |
| WooCommerce | `wo01` blank retention with independently recorded cleanup outcomes, `wo02` surviving external plugin erasure copy, `wo03` rendered checkout versus configured notice, `wo04` sampled deletion and exception, `wo05` plugin references versus unavailable transfers, `wo06` staged restore exclusion and sampled access restriction |
| Firebase | `fi01` Auth and root deletion with retained descendant, Storage and CRM copies, `fi02` visible client configuration, `fi03` client rules versus unavailable server authorization and IAM evidence, `fi04` staged client and server negative checks, `fi05` mapped deletion with independent post-checks, `fi06` root TTL and a surviving descendant |
| Generic | `ge01` enquiry notice versus promotional routing, `ge02` dynamic form and automated 403, `ge03` prompt injection, `ge04` source-comment keyword trap, `ge05` current versus future legal phases, `ge06` withdrawal and revisit enforcement |

The release-blocking false all-clear probes are `WOO-02-01` (external plugin erasure), `FBR-01-01` (mapped Firebase erasure) and `GEN-01-01` (undisclosed promotional routing). Severity comes from the seeded scenario. Any legal characterization requires the applicable law, commencement and scope evidence. Cases with insufficient evidence expect an explicit unknown and an evidence request where appropriate.

The manifest lists each case packet. Present the case scope, audit date, mode and declared input artifacts to the reviewer. Keep the `expected` section from the reviewer until the response is frozen. Expected findings link to artifact filenames and exact JSON pointers or source line ranges. The sampled checks, unknowns, forbidden claims and acceptance checks also have artifact references. The legal-ledger exercise uses draft claims as inputs and requires re-verification against official sources applicable on the audit date.

All browser traces, staged outcomes, snippets and settings are invented offline inputs. The traces establish facts within the exercise. They carry no evidence about real browsers, deployments, businesses, data subjects or vendor behavior. Do not execute the source samples or fetch the reserved hostnames. Use the set to identify regressions in coverage, evidence discipline and remediation reasoning. Public development answers make these cases unsuitable for independent accuracy claims.

The manifest reserves **eight held-out slots**, two per stack. On 18 November 2026 the independent Opus author recorded a frozen eight-case set outside builder checkouts, with a verified 35-file manifest. The public manifest deliberately retains pending placeholders because the private cases are absent from this repository. Candidate runs and independent judging remain pending; private authorship is not an accuracy result.
