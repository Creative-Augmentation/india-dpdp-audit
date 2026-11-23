"""Check public synthetic fixtures for obvious non-fixture URLs and identifiers.

Only the listed fixture paths are scanned. A finding calls for review or
redaction. The checks are heuristic and provide no privacy guarantee.
"""

from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TREES = ("evals/cases", "benchmark/cases", "benchmark/sites", "checks/fixtures")
EXAMPLE_RECORD = "skills/india-dpdp-audit/assets/example-audit.json"
# The example audit cites this exact official MeitY publication. Keep exceptions
# limited to individually reviewed primary legal or vendor citations.
OFFICIAL_CITATIONS = {
    "https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf",
}
RESERVED_SUFFIXES = (".test", ".example", ".invalid")
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
URL = re.compile(r"(?<![\w:/])(?:[a-z][a-z0-9+.-]*:)?//[a-z0-9\[][^\"'<>\s`\\]*", re.I)
EMAIL = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@([a-z0-9-]+(?:\.[a-z0-9-]+)*)", re.I)
MOBILE = re.compile(r"(?<![\w.+-])(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?![\w.-])")
AADHAAR_LIKE = re.compile(r"(?<![\w.+-])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\w.-])")


def reserved_hostname(hostname):
    host = (hostname or "").lower().rstrip(".")
    return host in LOCAL_HOSTS or host.endswith(RESERVED_SUFFIXES)


def disallowed_url(url):
    candidate = url.rstrip(".,;:!?)]}")
    if candidate in OFFICIAL_CITATIONS:
        return False
    try:
        parts = urlsplit(candidate)
        return parts.username is not None or not reserved_hostname(parts.hostname)
    except ValueError:
        return True


def findings(text):
    if any(disallowed_url(match.group()) for match in URL.finditer(text)):
        yield "non-fixture URL"
    if any(not reserved_hostname(match.group(1)) for match in EMAIL.finditer(text)):
        yield "non-fixture email"
    if MOBILE.search(text):
        yield "possible Indian mobile number"
    if AADHAAR_LIKE.search(text):
        yield "possible Aadhaar-like number"


def fixture_paths(root):
    for relative_tree in FIXTURE_TREES:
        tree = root / relative_tree
        for path in sorted(tree.rglob("*")):
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink() or path.is_file():
                yield path
    yield root / EXAMPLE_RECORD


def check(root):
    for path in fixture_paths(root):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            yield relative, "non-local fixture path"
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            yield relative, "unreadable fixture text"
            continue
        for rule in findings(text):
            yield relative, rule


def main():
    violations = list(check(ROOT))
    for path, rule in violations:
        print(f"{path}: {rule}", file=sys.stderr)
    if violations:
        print("Inspect and redact public fixtures as needed. Matches are heuristic.", file=sys.stderr)
        return 1
    print("Public fixture hygiene checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
