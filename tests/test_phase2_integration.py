"""Live loopback regression checks for the collector and merchant CLI."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_phase2_validation import validate_record


ACTIONS = {
    "reject": 'button[data-choice=denied]:has-text("Reject")',
    "accept": "button[data-choice=granted]",
    "withdraw": 'button[data-choice=denied]:has-text("Withdraw")',
}
EVENT_PATH = "/events/optional"
SENTINEL = "fixture-sensitive-136799"

def chromium_installed():
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).is_file()
    except (Error, OSError):
        return False


def load_lab():
    spec = importlib.util.spec_from_file_location("phase2_lab", ROOT / "benchmark/sites/serve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InlineFixtureHandler(BaseHTTPRequestHandler):
    def reply(self, status, content_type, body=b""):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code="-", size="-"):
        pass


@unittest.skipUnless(chromium_installed(), "Playwright with Chromium is required")
class Phase2IntegrationTests(unittest.TestCase):
    def setUp(self):
        lab = load_lab()
        # Keep test-only HTTP and DNS overrides inside the existing loopback fixture harness.
        async def fixture_addresses(origin):
            self.assertEqual(urlsplit(origin).hostname, "merchant.test")
            return ("127.0.0.1",)

        for override in (patch("collector.browser._require_https"),
                         patch("collector.browser._public_addresses", side_effect=fixture_addresses)):
            override.start()
            self.addCleanup(override.stop)
        self.lab_origin = self.start_server(lab.FixtureHandler)

    def start_server(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.shutdown)
        return f"http://merchant.test:{server.server_port}"

    def collect_packet(self, path, *, origin=None, **options):
        from collector.browser import collect

        origin = origin or self.lab_origin
        return collect(
            origin + path,
            authorized_origin=origin,
            authorization={"attested": True, "interactions": list(options.get("actions", {}))},
            settle_ms=500,
            **options,
        )

    def collect(self, path, **options):
        return {item["phase"]: item for item in self.collect_packet(path, **options)["observations"]}

    def assert_optional_requests(self, phases, expected):
        counts = {
            phase: sum(
                request["path"] == EVENT_PATH
                and request["disposition"] == "observed"
                and request["status"] == 204
                for request in item["requests"]
            )
            for phase, item in phases.items()
        }
        self.assertEqual({phase: counts[phase] for phase in expected}, expected)
        for phase in expected:
            self.assertEqual(phases[phase]["status"], "observed", phase)

    def test_consent_requests_and_persistence(self):
        phases = self.collect(
            "/consent/gated",
            actions=ACTIONS,
            safe_request_paths=[EVENT_PATH],
        )
        self.assert_optional_requests(
            phases,
            {
                "initial": 0,
                "reject": 0,
                "revisit_after_reject": 0,
                "accept": 1,
                "revisit_after_accept": 1,
                "withdraw": 0,
                "revisit_after_withdraw": 0,
            },
        )
        for phase, expected in [
            ("initial", 0),
            ("revisit_after_reject", 1),
            ("revisit_after_accept", 1),
            ("revisit_after_withdraw", 1),
        ]:
            self.assertEqual(phases[phase]["storage"]["local"], expected, phase)
        self.assertEqual(phases["initial_before_accept"]["storage"]["local"], 0)
        self.assertNotIn("source=gated", json.dumps(phases))

    def test_early_requests_survive_rejection_and_runs_start_fresh(self):
        phases = self.collect(
            "/consent/early",
            actions={"reject": ACTIONS["reject"]},
            safe_request_paths=[EVENT_PATH],
        )
        self.assert_optional_requests(
            phases, {"initial": 1, "reject": 0, "revisit_after_reject": 1}
        )
        self.assertEqual(phases["revisit_after_reject"]["storage"]["local"], 1)
        fresh = self.collect("/consent/early", safe_request_paths=[EVENT_PATH])
        self.assertEqual(fresh["initial"]["storage"]["local"], 0)
        self.assertEqual(fresh["reject"]["status"], "not_attempted")

    def test_choices_and_revisits_keep_the_question_from_missing_page_resources(self):
        from collector.audit_record import build_audit_record
        from merchant.report import render_summary

        lab = load_lab()
        foreign_hits = []

        class Foreign(lab.FixtureHandler):
            def do_GET(self):
                foreign_hits.append(self.path)
                self.reply(200, "application/javascript", b"/* synthetic page resource */")

        foreign = self.start_server(Foreign)

        class Consent(InlineFixtureHandler):
            def do_GET(self):
                if self.path != "/choice":
                    return self.send_error(404)
                script = ""
                if "visited=1" not in self.headers.get("Cookie", ""):
                    script = f'<script src="{foreign}/tag.js"></script>'
                page = f"""<!doctype html>{script}
                    <button id="reject" type="button">Reject</button>
                    <button id="accept" type="button">Accept</button>
                    <button id="withdraw" type="button">Withdraw</button>
                    <script>document.cookie = 'visited=1';</script>
                """
                self.reply(200, "text/html", page.encode())

        packet = self.collect_packet(
            "/choice", origin=self.start_server(Consent),
            actions={"reject": "#reject", "accept": "#accept", "withdraw": "#withdraw"},
        )
        phases = {item["phase"]: item for item in packet["observations"]}
        for phase in ("initial", "initial_before_accept"):
            self.assertIn("out_of_scope_origin", phases[phase]["reasons"])
        for phase in ("reject", "accept", "withdraw"):
            with self.subTest(phase=phase):
                self.assertEqual(phases[phase]["requests"], [])
        for phase in ("reject", "accept", "withdraw", "revisit_after_reject",
                      "revisit_after_accept", "revisit_after_withdraw"):
            with self.subTest(phase=phase):
                self.assertEqual(phases[phase]["status"], "partial")
                self.assertEqual(phases[phase]["reasons"], ["page_resources_incomplete"])
        self.assertEqual(foreign_hits, [])
        summary, _ = render_summary(packet, build_audit_record(packet))
        for label in ("After rejection", "After acceptance", "After withdrawal",
                      "Revisit after rejection", "Revisit after acceptance", "Revisit after withdrawal"):
            self.assertIn(f"**{label}.** Could not verify tracking after the choice", summary)

    def test_rendered_form_and_notice_without_submission(self):
        phases = self.collect("/dynamic", notice_selectors=["#contact-shell p"])
        initial = phases["initial"]
        self.assertEqual(initial["status"], "observed")
        self.assertEqual(initial["page_status"], 200)
        self.assertEqual(len(initial["forms"]), 1)
        form = initial["forms"][0]
        self.assertEqual(len(form["fields"]), 1)
        self.assertTrue(form["described_by_visible_element"])
        self.assertTrue(form["fields"][0]["required"])
        self.assertEqual(initial["notices"][0]["visible_count"], 1)
        self.assertTrue(all(item["method"] in {"GET", "HEAD"} for item in initial["requests"]))

    def test_blocked_policy_and_inert_reference(self):
        blocked = self.collect("/policy/blocked")["initial"]
        self.assertEqual(blocked["page_status"], 403)
        self.assertEqual(blocked["status"], "blocked")
        unknown = self.collect("/unknown")["initial"]
        self.assertEqual(unknown["status"], "observed")
        self.assertNotIn("measurement.example.test", json.dumps(unknown))
        self.assertNotIn("intake.invalid", json.dumps(unknown))

    def test_empty_successful_document_is_partial(self):
        lab = load_lab()

        class Blank(lab.FixtureHandler):
            def do_GET(self):
                self.reply(200, "text/html", b"<!doctype html><body> \n </body>")

        initial = self.collect("/blank", origin=self.start_server(Blank))["initial"]
        self.assertEqual(initial["page_status"], 200)
        self.assertEqual(initial["status"], "partial")
        self.assertIn("empty_document", initial["reasons"])

    def test_method_override_headers_are_omitted_from_forwarding(self):
        observed_headers = []

        class Headers(InlineFixtureHandler):
            def do_GET(self):
                if self.path == "/":
                    page = b"""<!doctype html><p>Sample</p><script>
                        fetch('/headers', {headers: {'X-HTTP-Method-Override': 'HEAD',
                            'X-HTTP-Method': 'HEAD', 'X-Method-Override': 'HEAD',
                            'X-Fixture': 'kept'}});
                        </script>"""
                    self.reply(200, "text/html", page)
                elif self.path == "/headers":
                    observed_headers.append({name.lower(): value for name, value in self.headers.items()})
                    self.reply(204, "text/plain")
                else:
                    self.send_error(404)

        initial = self.collect("/", origin=self.start_server(Headers))["initial"]
        self.assertEqual(initial["status"], "observed")
        self.assertEqual(len(observed_headers), 1)
        self.assertEqual(observed_headers[0]["x-fixture"], "kept")
        for name in ("x-http-method-override", "x-http-method", "x-method-override"):
            self.assertNotIn(name, observed_headers[0])

    def test_request_interception_and_redaction(self):
        from collector.audit_record import build_audit_record

        lab = load_lab()
        foreign_hits = []
        write_hits = []

        class Foreign(lab.FixtureHandler):
            def do_GET(self):
                foreign_hits.append(self.path)
                self.reply(204, "text/plain")

        foreign = self.start_server(Foreign)

        class Boundary(lab.FixtureHandler):
            def do_GET(self):
                if self.path == "/boundary":
                    page = f"""
                    <!doctype html>
                    <script src="/boundary.js"></script>
                    <form action="/{SENTINEL}"><input name="{SENTINEL}" value="{SENTINEL}"></form>
                    <p>{SENTINEL}</p>
                    """
                    self.reply(200, "text/html; charset=utf-8", page.encode())
                elif self.path == "/boundary.js":
                    script = f"""
                    localStorage.setItem("{SENTINEL}", "{SENTINEL}");
                    document.cookie = "{SENTINEL}={SENTINEL}";
                    fetch("{foreign}/{SENTINEL}?value={SENTINEL}").catch(() => {{}});
                    fetch("/asset?value={SENTINEL}").catch(() => {{}});
                    fetch("/write", {{method: "POST", body: "{SENTINEL}"}}).catch(() => {{}});
                    """
                    self.reply(200, "application/javascript", script.encode())
                elif self.path.startswith("/asset?"):
                    self.reply(204, "text/plain")
                elif self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", f"{foreign}/{SENTINEL}")
                    self.end_headers()
                else:
                    super().do_GET()

            def do_POST(self):
                write_hits.append(self.path)
                self.reply(204, "text/plain")

            def reply(self, status, content_type, body=b""):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        origin = self.start_server(Boundary)
        packet = self.collect_packet(
            "/boundary", origin=origin, notice_selectors=["p"], safe_request_paths=["/asset"]
        )
        initial = packet["observations"][0]
        self.assertEqual(initial["storage"]["local"], 1)
        self.assertEqual(initial["storage"]["cookies"], 1)
        self.assertEqual(initial["notices"][0]["visible_count"], 1)
        self.assertEqual(len(initial["forms"]), 1)
        self.assertNotIn(SENTINEL, json.dumps(initial))
        self.assertTrue(any(
            row["path"] == "/asset" and row["status"] == 204
            for row in initial["requests"]
        ))
        with self.assertRaises(ValueError):
            self.collect(f"/boundary?value={SENTINEL}#{SENTINEL}", origin=origin)
        self.assertTrue(any(
            row["method"] == "POST" and row["disposition"] == "blocked"
            for row in initial["requests"]
        ))
        self.assertTrue(any(
            row["method"] == "POST" and row["attempt_evidence_status"] == "observed"
            and row["response_evidence_status"] == "unknown" for row in initial["requests"]
        ))
        self.assertTrue(any(
            row["disposition"] == "blocked" and row["origin"] is None
            and row.get("reason") == "out_of_scope_origin"
            for row in initial["requests"]
        ))
        self.assertEqual(write_hits, [])
        self.assertEqual(foreign_hits, [])
        record = build_audit_record(packet)
        validate_record(self, record)
        gap, = [item for item in record["findings"] if item["evidence_status"] == "observed_gap"]
        self.assertIn("Unlabeled", gap["title"])
        self.assertNotIn(SENTINEL, json.dumps(record))

        redirect = self.collect("/redirect", origin=origin)["initial"]
        self.assertEqual(redirect["status"], "blocked")
        self.assertEqual(redirect["page_status"], 302)
        self.assertIn("redirect_suppressed", redirect["reasons"])
        self.assertEqual(foreign_hits, [])
        self.assertNotIn(SENTINEL, json.dumps(redirect))

    def test_merchant_cli_requires_authority_and_publishes_bounded_outputs(self):
        from datetime import datetime, timedelta
        from importlib.metadata import version
        from merchant.__main__ import main

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "audit"
            invocation = [
                self.lab_origin + "/policy/blocked", "--output-dir", str(destination),
            ]
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as denied:
                main(invocation)
            self.assertEqual(denied.exception.code, 2)
            self.assertFalse(destination.exists())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([*invocation, "--authorized"]), 1)
            self.assertEqual(
                {item.name for item in destination.iterdir()}, {"evidence.json", "audit.json", "summary.md"}
            )
            evidence = json.loads((destination / "evidence.json").read_text())
            self.assertEqual(evidence["observations"][0]["page_status"], 403)
            authorization = evidence["authorization"]
            self.assertIs(authorization["attested"], True)
            self.assertEqual(authorization["origin"], self.lab_origin)
            self.assertEqual(authorization["interactions"], [])
            self.assertEqual(datetime.fromisoformat(authorization["attested_at"]).utcoffset(), timedelta())
            self.assertEqual(evidence["browser"]["playwright_version"], version("playwright"))
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            self.assertEqual(evidence["collector"]["revision"], head)
            summary = (destination / "summary.md").read_text()
            self.assertIn("could not verify", summary.lower())
            record = json.loads((destination / "audit.json").read_text())
            validate_record(self, record)
            self.assertTrue(all(item["evidence_status"] == "not_verified" for item in record["findings"]))
