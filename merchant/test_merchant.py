"""Test the command's authorization, output isolation and coverage reporting."""

import contextlib
import io
import json
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from merchant.__main__ import main


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
        fake_backend = types.ModuleType("collector.browser")
        fake_backend.collect = self.collect
        self.context(patch.dict("sys.modules", {"collector.browser": fake_backend}))
        self.stdout = self.context(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.context(contextlib.redirect_stderr(io.StringIO()))

    def context(self, manager):
        value = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return value

    def invoke(self, *args, target="https://example.com/contact"):
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
            ("https://example.com", "--consent-url", "https://other.example.com"),
            ("http://127.0.0.1:5123",),
            ("https://example.com/?token=private",),
        ]
        for target, *scope in options:
            with self.subTest(target=target), self.assertRaises(SystemExit) as error:
                self.invoke("--authorized", *scope, target=target)
            self.assertEqual(error.exception.code, 2)
        self.collect.assert_not_called()

    def test_partial_sample_keeps_evidence_and_gap_first_summary(self):
        status = self.invoke("--authorized", "--allow-loopback", "--reject-selector", "#deny",
                             "--allow-request-path", "/sample", target="http://127.0.0.1:5123")
        self.assertEqual(status, 0)
        self.collect.assert_called_once_with(
            "http://127.0.0.1:5123", authorized_origin="http://127.0.0.1:5123",
            actions={"reject": "#deny"}, consent_url=None, safe_request_paths=["/sample"],
            notice_selectors=[], allow_loopback=True,
        )
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        packet = self.output / "evidence.json"
        self.assertEqual(stat.S_IMODE(packet.stat().st_mode), 0o600)
        evidence = json.loads(packet.read_text())
        self.assertEqual(evidence, self.collect.return_value)
        report = (self.output / "summary.md").read_text()
        self.assertEqual(report, self.stdout.getvalue())
        self.assertLess(report.index("Gaps to verify"), report.index("Browser sample"))
        self.assertIn("After rejection.** Could not check", report)
        self.assertIn("1 marked blocked", report)
        self.assertNotIn("untrusted text", report)

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
        self.assertIn("Could not check any phase", report)
        self.assertNotIn("private browser diagnostics", report + evidence + self.stderr.getvalue())

    def test_all_blocked_run_has_no_usable_sample(self):
        self.collect.return_value = {"observations": [{"phase": "initial", "status": "blocked"}]}
        self.assertEqual(self.invoke("--authorized"), 1)
        self.assertIn("no usable sample", self.stdout.getvalue())
