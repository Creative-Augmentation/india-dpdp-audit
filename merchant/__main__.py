"""Collect a bounded sample of a merchant website with explicit authorization."""

import argparse
import json
import os
import sys
from pathlib import Path

from collector.audit_record import build_audit_record
from merchant.report import render_summary


def parse_origin(url: str) -> str:
    from collector.browser import _approved_url, _origin, _require_https

    origin = _origin(url)
    _approved_url(url, origin)
    _require_https(origin)
    return origin


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m merchant",
        description="Collect evidence from a website and interactions you are authorized to test."
    )
    parser.add_argument("url", metavar="URL", help="Entry page to sample")
    parser.add_argument("--authorized", action="store_true",
                        help="Confirm authorization for the target, specified requests and consent actions")
    parser.add_argument("--output-dir", required=True, type=Path, metavar="NEW_DIRECTORY",
                        help="New private directory for evidence.json, audit.json and summary.md")
    parser.add_argument("--consent-url", metavar="URL",
                        help="Same-origin page for consent observations (defaults to the entry page)")
    for action in ("accept", "reject", "withdraw"):
        parser.add_argument(f"--{action}-selector", metavar="CSS",
                            help=f"Explicit selector for a consent-only {action} button")
    parser.add_argument("--allow-request-path", action="append", default=[], metavar="/PATH",
                        help="Keep this known same-origin request path in evidence (repeatable)")
    parser.add_argument("--notice-selector", action="append", default=[], metavar="CSS",
                        help="Identify a notice element to sample (repeatable)")
    return parser


def write_private(path: Path, contents: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(contents)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    if not options.authorized:
        parser.error("--authorized is required before any collection can run.")
    try:
        from collector.browser import _approved_url, collect
    except ImportError:
        print("Collector unavailable. See merchant/README.md for setup.", file=sys.stderr)
        return 1

    try:
        origin = parse_origin(options.url)
        if options.consent_url is not None:
            _approved_url(options.consent_url, origin)
    except ValueError as error:
        parser.error(str(error))

    actions = {
        action: selector for action in ("accept", "reject", "withdraw")
        if (selector := getattr(options, f"{action}_selector")) is not None
    }
    try:
        options.output_dir.mkdir(mode=0o700)
    except OSError:
        print("Cannot create the private output directory. Its parent must exist and the directory must be new.",
              file=sys.stderr)
        return 1
    try:
        evidence = collect(
            options.url,
            authorized_origin=origin,
            authorization={"attested": options.authorized, "interactions": list(actions)},
            actions=actions,
            consent_url=options.consent_url,
            safe_request_paths=options.allow_request_path,
            notice_selectors=options.notice_selector,
        )
    except Exception:
        # Backend exceptions may include unredacted URLs, selectors or browser diagnostics.
        evidence = {"merchant_status": "collection-error"}
    audit_record = build_audit_record({**evidence, "authorized_origin": origin})
    report, usable = render_summary(evidence, audit_record)
    try:
        write_private(options.output_dir / "evidence.json", json.dumps(evidence, indent=2) + "\n")
        write_private(options.output_dir / "audit.json", json.dumps(audit_record, indent=2) + "\n")
        write_private(options.output_dir / "summary.md", report)
    except OSError:
        print("Could not finish writing outputs. Treat the run directory as incomplete.", file=sys.stderr)
        return 1
    print(report, end="")
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
