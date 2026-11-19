# Phase 2 collector evaluation

The live regression suite exercises the Python collector and merchant command on original synthetic pages served on ephemeral IPv4 loopback ports. A separate run exercised the pinned Vettam native browser engine on the five existing public fixture routes. Both use a 500 ms observation window and Chromium 145.0.7632.6. They use different consent controls and collection scopes, as recorded below.

## Run the local checks

Install the collector's pinned Python dependency and its Chromium browser. Then run the opt-in suite from the repository root.

```sh
python3 -m pip install -r collector/requirements.txt
python3 -m playwright install chromium
DPDP_RUN_BROWSER_TESTS=1 python3 -m unittest discover -s tests -p test_phase2_integration.py -v
```

The tests start and stop their loopback servers. With opt-in enabled, a missing dependency or unusable browser fails the run. The original fixture contract describes the deterministic page behavior. [Local browser collection fixtures](benchmark-collection-fixtures.md)

| Regression | Required observations |
| --- | --- |
| Gated consent | Optional requests by stage are initial 0, reject 0, revisit after reject 0, accept 1, revisit after accept 1, withdraw 0, revisit after withdrawal 0. Storage starts empty in the rejection and acceptance branches and has one local item at the revisits. |
| Early request and isolation | One optional request before any choice, zero during the reject action, and one on revisit after rejection. A separate run starts with empty storage. An unconfigured action is recorded as unattempted. |
| Rendered form and notice | JavaScript creates one form with one required field and a reference to a visible element. The supplied notice selector matches once. No submission occurs. |
| Blocked policy and inert reference | Record the HTTP 403 and blocked status. Static vendor and contact examples stay out of the persisted observations. |
| Scope and data minimisation | An independent receiving origin records zero requests after a direct third-party fetch attempt and a cross-origin redirect. The same-origin POST receiver records zero writes. Record the intercepted attempts and 302 status. Keep the explicitly permitted asset path and omit the injected query, field, notice, cookie and storage values. Reject query and fragment at the entry point. |
| Merchant command | Without authority the command leaves no output directory. An authorized, blocked visit returns the incomplete exit status and writes both the evidence packet and a summary that describes what could not be checked. |

## Pinned Vettam engine baseline

Vettam 2.1.0 at revision `d135d85d47c84486ad39032c88e0a696178bdcf7` was obtained separately. The baseline compiled the unchanged checkout using its installed TypeScript compiler and invoked `defaultEngine.scan` with its built-in banner heuristics. It used Node 22.14.0 and the same cached Chromium headless executable, with a rejecting loopback proxy for non-loopback destinations and DNS resolution disabled for non-loopback hosts. The original fixtures serve only local active resources and apply an origin-restricting content policy. The raw engine uses a fresh browser context per call and the comparison omitted tracker signature configuration supplied by the full scanner. Three repetitions of eight passes each produced the same request counts, click outcomes and record types. The complete CLI, rule mapper, vendor data and remediation text were outside the measured configuration. [Pinned engine source](https://github.com/Vettam/dpdp-compliance-scanner/blob/d135d85d47c84486ad39032c88e0a696178bdcf7/src/engine/playwright.ts) · [Component licence assessment](licensing/UPSTREAM_COMPATIBILITY.md)

| Fixture | Observed Vettam raw engine output | Python collector regression |
| --- | --- | --- |
| Early consent | 1 optional request on initial load and 1 in the reject pass. The reject pass reported a successful click and emitted storage evidence. Counts for that pass include its fresh page load. | Separate initial, click and revisit rows capture 1, 0 and 1 respectively. |
| Gated consent | 0 initial, 0 in the reject pass, 1 in the accept pass. Reject and accept reported successful clicks and emitted storage evidence. | Adds revisits after reject and accept, followed by withdrawal and a revisit that each capture zero optional requests. |
| Dynamic form | Emitted the document request, the script request, an embed and navigation metadata. The raw engine output had no rendered form or notice record for this page. | Captures rendered form structure and a configured visible notice match. |
| Blocked policy | Emitted a request and navigation metadata without HTTP status or a blocked-document indicator. | Retains the HTTP 403 and marks the visit blocked. |
| Inert vendor | Emitted the document request and navigation metadata. Observed zero third-party requests. | Treats the fixture's inert vendor reference as text outside the persisted evidence. |

Withdrawal, persistence across revisits, interception boundaries and redaction sentinels were evaluated by the Python regression suite only. The Vettam baseline recorded accept and reject as individual passes. It did not exercise a same-context continuation.

Prefer the original collector for this bounded prototype because it supplies the missing visit-status, rendered-structure and same-context evidence tested here. Consider any later upstream adapter against the transport-scope and redaction checks before using it with merchant targets. This experiment imported no Vettam implementation or data.

These results measure synthetic evidence capture and failure reporting. Legal judgment, remediation quality, platform coverage, complete third-party visibility and independently judged accuracy remain outside the run. The private cases were excluded.
