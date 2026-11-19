# Local browser evidence collector

Install the optional runtime in a virtual environment from the repository root.

```sh
python3 -m pip install -r collector/requirements.txt
python3 -m playwright install chromium
```

The merchant command calls `collector.browser.collect`. Callers obtain the owner's authorization for the site and every interaction, then pass an explicit attestation with the interaction names. The packet records the attestation, origin and UTC timestamp. Use a canonical HTTPS origin and one explicit public entry URL. An optional consent URL must be on the same origin. Use `allow_loopback=True` only for an explicitly authorized literal loopback fixture. Invalid input raises `ValueError`.

```python
from collector.browser import collect

packet = collect(
    "http://127.0.0.1:8123/consent/gated",
    authorized_origin="http://127.0.0.1:8123",
    authorization={"attested": True, "interactions": ["accept", "reject", "withdraw"]},
    allow_loopback=True,
    actions={
        "accept": "button:has-text('Accept')",
        "reject": "button:has-text('Reject')",
        "withdraw": "button:has-text('Withdraw')",
    },
    safe_request_paths=["/events/optional"],
)
```

Use selectors for owner-approved, visible top-level non-submit buttons. The collector invokes these buttons using synthetic browser clicks. Rejection and acceptance begin in separate clean Chromium contexts. Revisits are explicit same-URL top-level navigations in the same context as the preceding choice. Withdrawal follows a successful acceptance and revisit. Authentication, input filling, form submission, discovery, popup navigation and third-party resource delivery are outside this workflow. Same-origin GET or HEAD requests can still cause application-specific effects. Confirm that the authorized site and selected controls are suitable for anonymous sampling.

Chromium routes HTTP(S) requests through the collector. It denies other origins, redirects, write methods, unplanned navigations, service workers and WebSockets. The one-origin transport resolves public destinations before opening a tunnel and dials only the vetted numeric addresses while preserving HTTPS certificate validation for the original host. Its checks do not substitute for process- or network-level isolation. No third-party delivery means a banner that relies on outside scripts may be unavailable. A blocked attempt indicates a browser request attempt, with delivery prevented.

The packet contains UTC timing, browser provenance and a bounded record for each phase. Each phase may be `observed`, `partial`, `blocked`, or `not_attempted`. The record includes fixed reason codes, request method/type/status, browser storage counts, rendered form structure and visible-match counts for explicit CSS notice selectors. It omits page text, selectors, input values, raw paths and URLs, third-party hostnames, queries, fragments, headers and storage contents. Only explicitly approved literal request paths are included. Provide paths that contain no personal data. The collector reads form and notice structure from the rendered top-level document and collects no screenshots or browser traces.

The window defaults to 500 ms after navigation reaches DOM ready or the selected button is invoked. The request budget is 120 per run and the displayed form and notice structures have per-list limits. The collector does not identify the legal purpose of a request, determine the content of a notice, confirm the value or meaning of a storage entry, or infer compliance. A quiet sample gives evidence only for that browser path, context and window.
