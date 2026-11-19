# Merchant evidence command

Run from the repository root after installing the [collector dependencies](../collector/README.md). The current repository licence applies. Business use requires separate permission under the [current licence notice](../README.md#licence-and-contact).

```sh
python3 -m merchant https://store.example/contact \
  --authorized --output-dir audit-output/run-01
```

Create the parent directory first. The command writes `evidence.json`, a redacted browser packet, and `audit.json`, a record for `audit.py validate`, to a new private directory. It prints the same `summary.md` it saves, with observed gaps and open questions in separate sections and a next step for each. Keep the outputs local and review them before sharing.

Provide `--authorized` only when you have authority over the HTTPS domain and all specified test interactions. IP-literal targets are refused. In a controlled environment, select consent-only buttons with `--accept-selector`, `--reject-selector` and `--withdraw-selector`. For a separate consent page on the same origin use `--consent-url`. A repeatable `--notice-selector` identifies a rendered notice to sample. A repeatable `--allow-request-path` retains a known, non-sensitive same-origin request path in evidence. Omit paths containing identifiers or secrets.

The browser starts in isolated contexts and samples the supplied pages. Its access boundary can prevent site features that depend on other origins from working. Use a controlled fixture or staging environment for consent actions. The summary prioritizes collection failures and owner verification and makes no automatic legal determination. An exit code of zero indicates at least one usable sample, including partial runs. An exit code of one indicates no usable sample or an output/setup failure. Argument errors use exit code two.
