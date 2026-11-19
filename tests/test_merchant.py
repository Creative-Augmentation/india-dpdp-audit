"""Test the command's authorization, output isolation and coverage reporting."""

import contextlib
import io
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from merchant.__main__ import main
from test_phase2_validation import validate_record


class MerchantTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / "run"
        self.collect = Mock(return_value={
            "observations": [
                {"phase": "initial", "status": "observed", "forms": [{"fields": [{}]}],
                 "requests": [{"disposition": "blocked"}]},
                {"phase": "reject", "status": "blocked", "reasons": ["untrusted text"]},
            ],
        })
        self.context(patch("collector.browser.collect", self.collect))
        self.stdout = self.context(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.context(contextlib.redirect_stderr(io.StringIO()))

    def context(self, manager):
        value = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return value

    def invoke(self, *args, target="https://merchant.test/contact"):
        return main([target, "--output-dir", str(self.output), *args])

    def test_requires_authorization_before_creating_outputs_or_collecting(self):
        with self.assertRaises(SystemExit) as error:
            self.invoke()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("--authorized is required", self.stderr.getvalue())
        self.assertFalse(self.output.exists())
        self.collect.assert_not_called()

    def test_refuses_different_consent_origin_and_requires_loopback_flag(self):
        options = [
            ("https://merchant.test", "--consent-url", "https://other.test"),
            ("https://merchant.test/?token=private",),
        ]
        for target, *scope in options:
            with self.subTest(target=target), self.assertRaises(SystemExit) as error:
                self.invoke("--authorized", *scope, target=target)
            self.assertEqual(error.exception.code, 2)
        self.collect.assert_not_called()

    def test_literal_targets_are_refused_before_output(self):
        for url in ("http://127.0.0.1:5123/", "https://1.1.1.1/", "https://[2606:4700::1111]/"):
            for target, scope in ((url, ()), ("https://merchant.test/", ("--consent-url", url))):
                with self.subTest(target=target, scope=scope), self.assertRaises(SystemExit) as error:
                    self.invoke("--authorized", *scope, target=target)
                self.assertEqual(error.exception.code, 2)
                self.assertFalse(self.output.exists())
        self.assertIn("authorize a domain name; IP-literal targets are not supported", self.stderr.getvalue())
        self.collect.assert_not_called()

    def test_refuses_noncanonical_entry_and_consent_urls_before_output(self):
        for url in ("https://Merchant.test/contact", "https://merchant.test:443/",
                    "https://merchant.test/a/../b", "https://merchant.test/a%20b"):
            for target, options in ((url, ()), ("https://merchant.test", ("--consent-url", url))):
                with self.subTest(target=target, options=options):
                    with self.assertRaises(SystemExit) as error:
                        self.invoke("--authorized", *options, target=target)
                    self.assertEqual(error.exception.code, 2)
                    self.assertFalse(self.output.exists())
        self.collect.assert_not_called()

    def test_partial_sample_keeps_evidence_and_reports_open_questions(self):
        status = self.invoke("--authorized", "--reject-selector", "#deny", "--allow-request-path", "/sample")
        self.assertEqual(status, 0)
        self.collect.assert_called_once_with(
            "https://merchant.test/contact", authorized_origin="https://merchant.test",
            authorization={"attested": True, "interactions": ["reject"]},
            actions={"reject": "#deny"}, consent_url=None, safe_request_paths=["/sample"],
            notice_selectors=[],
        )
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        packet = self.output / "evidence.json"
        self.assertEqual(stat.S_IMODE(packet.stat().st_mode), 0o600)
        evidence = json.loads(packet.read_text())
        self.assertEqual(evidence, self.collect.return_value)
        report = (self.output / "summary.md").read_text()
        self.assertEqual(report, self.stdout.getvalue())
        self.assertLess(report.index("Open questions"), report.index("Browser sample"))
        self.assertIn("After rejection.** Could not verify", report)
        self.assertIn("1 marked blocked", report)
        self.assertNotIn("untrusted text", report)
        self.assertNotRegex(report.lower(), r"\b(?:compliant|no gaps)\b")
        audit = self.output / "audit.json"
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)
        record = json.loads(audit.read_text())
        validate_record(self, record)
        self.assertTrue(all(item["evidence_status"] == "not_verified" for item in record["findings"]))

    def test_summary_includes_accept_baseline_question_and_sampling_window(self):
        self.collect.return_value["observations"].append(
            {"phase": "initial_before_accept", "status": "blocked"}
        )
        self.collect.return_value["settle_ms"] = 500
        self.assertEqual(self.invoke("--authorized"), 0)
        report = self.stdout.getvalue()
        self.assertIn("Initial consent page before acceptance.** Could not verify", report)
        self.assertIn("500 ms after DOMContentLoaded or the selected button click", report)
        self.assertIn("Activity may occur after a quiet sample.", report)

    def test_refuses_existing_output_before_collecting(self):
        self.output.mkdir()
        previous = self.output / "summary.md"
        previous.write_text("previous")
        self.assertEqual(self.invoke("--authorized"), 1)
        self.assertEqual(previous.read_text(), "previous")
        self.collect.assert_not_called()

    def test_backend_error_details_are_not_printed_or_written(self):
        self.collect.side_effect = RuntimeError("private browser diagnostics")
        self.assertEqual(self.invoke("--authorized"), 1)
        report = (self.output / "summary.md").read_text()
        evidence = (self.output / "evidence.json").read_text()
        self.assertIn("Could not verify", report)
        self.assertNotIn("private browser diagnostics", report + evidence + self.stderr.getvalue())

    def test_all_blocked_run_has_no_usable_sample(self):
        self.collect.return_value = {"observations": [{"phase": "initial", "status": "blocked"}]}
        self.assertEqual(self.invoke("--authorized"), 1)
        self.assertIn("no usable sample", self.stdout.getvalue())
