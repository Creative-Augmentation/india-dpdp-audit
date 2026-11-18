"""Collect a bounded sample of a merchant website with explicit authorization."""

import argparse
import ipaddress
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from merchant.report import render_summary


def parse_origin(url: str, *, allow_loopback: bool) -> str:
    if any(ord(character) <= 32 or ord(character) == 127 for character in url):
        raise ValueError("Use an absolute URL without whitespace or control characters.")
    if any(character in url for character in "\\?#"):
        raise ValueError("Use a URL without backslashes, a query string, or a fragment.")
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port
    if parts.scheme not in {"http", "https"} or not host or not parts.netloc:
        raise ValueError("Use an absolute HTTPS URL.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Credentials in URLs are forbidden.")
    if not host.isascii() or "%" in host:
        raise ValueError("Use a literal IP address or an ASCII domain name.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and address.is_loopback:
        if not allow_loopback:
            raise ValueError("Loopback targets require --allow-loopback for local fixtures.")
    elif parts.scheme != "https":
        raise ValueError("HTTPS is required outside literal loopback fixtures.")

    authority = f"[{host}]" if ":" in host else host
    default_port = 443 if parts.scheme == "https" else 80
    if port is not None and port != default_port:
        authority += f":{port}"
    return f"{parts.scheme}://{authority}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m merchant",
        description="Collect evidence from a website and interactions you are authorized to test."
    )
    parser.add_argument("url", metavar="URL", help="Entry page to sample")
    parser.add_argument("--authorized", action="store_true",
                        help="Confirm authorization for the target, specified requests and consent actions")
    parser.add_argument("--allow-loopback", action="store_true",
                        help="Allow a literal loopback address for local fixtures")
    parser.add_argument("--output-dir", required=True, type=Path, metavar="NEW_DIRECTORY",
                        help="New private directory for evidence.json and summary.md")
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
        origin = parse_origin(options.url, allow_loopback=options.allow_loopback)
        if options.consent_url and parse_origin(
            options.consent_url, allow_loopback=options.allow_loopback
        ) != origin:
            parser.error("--consent-url must have the same origin as URL.")
    except ValueError as error:
        parser.error(str(error))

    actions = {
        action: selector for action in ("accept", "reject", "withdraw")
        if (selector := getattr(options, f"{action}_selector")) is not None
    }
    try:
        from collector.browser import collect
    except ImportError:
        print("Collector unavailable. See merchant/README.md for setup.", file=sys.stderr)
        return 1

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
            actions=actions,
            consent_url=options.consent_url,
            safe_request_paths=options.allow_request_path,
            notice_selectors=options.notice_selector,
            allow_loopback=options.allow_loopback,
        )
    except Exception:
        # Backend exceptions may include unredacted URLs, selectors or browser diagnostics.
        evidence = {"merchant_status": "collection-error"}
    report, usable = render_summary(evidence)
    try:
        write_private(options.output_dir / "evidence.json", json.dumps(evidence, indent=2) + "\n")
        write_private(options.output_dir / "summary.md", report)
    except OSError:
        print("Could not finish writing outputs. Treat the run directory as incomplete.", file=sys.stderr)
        return 1
    print(report, end="")
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
