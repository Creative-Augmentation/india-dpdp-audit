from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_fixture_hygiene.py"
SPEC = importlib.util.spec_from_file_location("fixture_hygiene", SCRIPT)
HYGIENE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HYGIENE)


class FixtureHygieneTests(unittest.TestCase):
    def test_fixture_hosts_and_exact_official_citation_are_allowed(self):
        citation = next(iter(HYGIENE.OFFICIAL_CITATIONS))
        sample = (
            "https://site.example.test/ https://site.example/a http://127.0.0.1:8080/ "
            "http://localhost:8000/ //gallery.example.test/image.png "
            "mailto:sample@site.invalid dev@localhost\n"
            f"[Official citation]({citation})."
        )
        self.assertEqual(list(HYGIENE.findings(sample)), [])

    def test_unreviewed_urls_and_addresses_are_flagged(self):
        for item in (
            "https://example.com/path",
            "//images.example.com/pic.png",
            "https://site.invalid.example.com/",
            "https://www.meity.gov.in/unreviewed",
            "https://token@site.invalid/path",
        ):
            with self.subTest(item=item):
                self.assertEqual(list(HYGIENE.findings(item)), ["non-fixture URL"])
        self.assertEqual(list(HYGIENE.findings("mailto:sample@example.com")), ["non-fixture email"])
        self.assertEqual(list(HYGIENE.findings("sample@www.meity.gov.in")), ["non-fixture email"])

    def test_digit_patterns_have_small_boundaries(self):
        mobile = "98" + "0000" + "0000"
        aadhaar_like = "2345" + " 0000" + " 0000"
        self.assertEqual(list(HYGIENE.findings(f"({mobile})")), ["possible Indian mobile number"])
        self.assertEqual(list(HYGIENE.findings("+91 " + mobile)), ["possible Indian mobile number"])
        self.assertEqual(list(HYGIENE.findings(aadhaar_like)), ["possible Aadhaar-like number"])
        self.assertEqual(list(HYGIENE.findings(f"REV{mobile}X 2026-11-18")), [])

    def test_cli_scans_owned_fixtures_without_reflecting_matches(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in (*HYGIENE.FIXTURE_TREES, str(Path(HYGIENE.EXAMPLE_RECORD).parent)):
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / HYGIENE.EXAMPLE_RECORD).write_text('{"url":"https://doc.example.test"}')
            outside_scope = root / "local-audit.md"
            outside_scope.write_text("https://outside.example.com")
            fixture = root / "benchmark/sites/demo.txt"
            matched = ("987" + "0000000", "https://sample.example.com/path", "sample@example.com")
            fixture.write_text("\n".join(matched))
            stdout = StringIO()
            stderr = StringIO()
            with patch.object(HYGIENE, "ROOT", root), redirect_stderr(stderr), redirect_stdout(stdout):
                self.assertEqual(HYGIENE.main(), 1)
            result = stdout.getvalue() + stderr.getvalue()
            self.assertIn("benchmark/sites/demo.txt: possible Indian mobile number", result)
            self.assertIn("benchmark/sites/demo.txt: non-fixture URL", result)
            self.assertIn("benchmark/sites/demo.txt: non-fixture email", result)
            for value in (*matched, outside_scope.name, "outside.example.com"):
                self.assertNotIn(value, result)
            fixture.write_text("https://shop.example.test/")
            self.assertEqual(list(HYGIENE.check(root)), [])


if __name__ == "__main__":
    unittest.main()
