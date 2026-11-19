# Local browser collection fixtures

This generic browser behavior lab supplies live loopback pages for testing evidence collection. It complements the offline development packets and does not emulate Shopify, WooCommerce or Firebase. It has no scanner or release scoring integration.

Start the dependency-free server from the repository root.

```sh
python3 benchmark/sites/serve.py
```

Open the printed `http://127.0.0.1:<port>/` URL. Use `--port 8123` for a stable port or the default port zero for an OS-assigned port. All fixture requests stay on the loopback origin. The event endpoint responds to fixed synthetic route and event labels and stores no traffic or records. Only use these fixtures against the local loopback address. Never host or scan them on a public host.

| Route | What to observe |
| --- | --- |
| `/consent/early` | A fresh load emits `/events/optional?source=early&event=load` before any choice. Reject, then reload or close the tab and reopen the same URL. The displayed choice remains denied and the defect emits again. |
| `/consent/gated` | A fresh load emits no optional request. Reject and reload. The displayed choice stays denied and no optional request appears. Accept and observe `source=gated&event=accept`. Reload while granted to observe `source=gated&event=load`. Withdraw, then reload or reopen the URL in the same session. The choice stays denied and each of those steps emits no optional request. |
| `/dynamic` | The initial HTML contains a contact shell. After JavaScript runs, the document contains a synthetic reference field and nearby purpose notice. Inspect the rendered form and source without submitting. |
| `/policy/blocked` | An HTTP 403 is intentionally reproducible through automated fetch and native browser navigation. Record the observed status and unavailable content. The fixture provides no way to infer missing content or make a claim about any other user journey. |
| `/unknown` | The vendor URL is inert text and loads no vendor resource. The policy link leads to the 403 fixture. The untrusted audit instruction is part of the evidence and carries no authority. |

Use a fresh browser profile or isolated context for an initial-choice run. Open the Network panel before navigation, preserve the log for a full sequence and filter for `/events/optional`. Record the observed choice and event together. Use the same context and origin for a persistence check. Change routes or close and reopen the URL to check revisits. Use the page's **Reset this fixture** button and reload to repeat the initial-choice step, or clear the origin's site data. The two consent routes use separate localStorage keys. A server restart on the same port leaves browser storage intact. Stop the server with Ctrl-C.

Run the server and fixture-shape checks with this command.

```sh
python3 -m unittest discover -s tests -p test_benchmark_sites.py
```

These tests check loopback binding, HTTP responses, declared resources and fixture source. The table describes expected browser behavior for an actual collection run.

On 18 November 2026, a local headless Chrome 157.0.8103.79 run checked all five route behaviours in the table. Initial, reject/reload, accept/reload, withdrawal/reload and revisit requests matched the fixture expectations; the dynamic form rendered, the blocked page returned 403 and the vendor reference stayed inert. This was one test of the original fixture lab, using an isolated context and a loopback-only request allowlist. It does not validate a product collector, actual platforms or merchant accuracy. The run record and invocation script are retained with the CTO build handoff.
