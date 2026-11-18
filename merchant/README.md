# Merchant evidence command

Run from the repository root after installing the [collector dependencies](../collector/README.md). The current repository licence applies. Business use requires separate permission under the [current licence notice](../README.md#licence-and-contact).

```sh
python3 -m merchant https://store.example/contact \
  --authorized --output-dir audit-output/run-01
```

Create the parent directory first. The command creates a new private directory for each run and prints the same gap-first summary it writes to `summary.md`. The bounded browser evidence is in `evidence.json`. Keep both files local and review them before sharing.

Provide `--authorized` only when you have authority over the origin and all specified test interactions. In a controlled environment, select consent-only buttons with `--accept-selector`, `--reject-selector` and `--withdraw-selector`. For a separate consent page on the same origin use `--consent-url`. A repeatable `--notice-selector` identifies a rendered notice to sample. A repeatable `--allow-request-path` retains a known, non-sensitive same-origin request path in evidence. Omit paths containing identifiers or secrets. Literal loopback fixture URLs require `--allow-loopback`.

The browser starts in isolated contexts and samples the supplied pages. Its access boundary can prevent site features that depend on other origins from working. Use a controlled fixture or staging environment for consent actions. The summary prioritizes collection failures and owner verification and makes no automatic legal determination. An exit code of zero indicates at least one usable sample, including partial runs. An exit code of one indicates no usable sample or an output/setup failure. Argument errors use exit code two.
