"""Live loopback regression checks for the collector and merchant CLI."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIONS = {
    "reject": 'button[data-choice=denied]:has-text("Reject")',
    "accept": "button[data-choice=granted]",
    "withdraw": 'button[data-choice=denied]:has-text("Withdraw")',
}
EVENT_PATH = "/events/optional"
SENTINEL = "fixture-sensitive-136799"


def load_lab():
    spec = importlib.util.spec_from_file_location("phase2_lab", ROOT / "benchmark/sites/serve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(os.environ.get("DPDP_RUN_BROWSER_TESTS") == "1", "live browser tests require opt-in")
class Phase2IntegrationTests(unittest.TestCase):
    def setUp(self):
        lab = load_lab()
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
        return f"http://127.0.0.1:{server.server_port}"

    def collect(self, path, *, origin=None, **options):
        from collector.browser import collect

        origin = origin or self.lab_origin
        result = collect(
            origin + path,
            authorized_origin=origin,
            allow_loopback=True,
            settle_ms=500,
            **options,
        )
        return {item["phase"]: item for item in result["observations"]}

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

    def test_request_interception_and_redaction(self):
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
        initial = self.collect(
            "/boundary", origin=origin, notice_selectors=["p"], safe_request_paths=["/asset"]
        )["initial"]
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
            row["disposition"] == "blocked" and row["origin"] is None
            and row.get("reason") == "out_of_scope_origin"
            for row in initial["requests"]
        ))
        self.assertEqual(write_hits, [])
        self.assertEqual(foreign_hits, [])

        redirect = self.collect("/redirect", origin=origin)["initial"]
        self.assertEqual(redirect["status"], "blocked")
        self.assertEqual(redirect["page_status"], 302)
        self.assertIn("redirect_suppressed", redirect["reasons"])
        self.assertEqual(foreign_hits, [])
        self.assertNotIn(SENTINEL, json.dumps(redirect))

    def test_merchant_cli_requires_authority_and_publishes_bounded_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "audit"
            invocation = [
                sys.executable, "-m", "merchant", self.lab_origin + "/policy/blocked",
                "--allow-loopback", "--output-dir", str(destination),
            ]
            denied = subprocess.run(
                invocation, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertFalse(destination.exists())
            run = subprocess.run(
                [*invocation, "--authorized"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(
                {item.name for item in destination.iterdir()}, {"evidence.json", "summary.md"}
            )
            evidence = json.loads((destination / "evidence.json").read_text())
            self.assertEqual(evidence["observations"][0]["page_status"], 403)
            summary = (destination / "summary.md").read_text()
            self.assertIn("could not check", summary.lower())
