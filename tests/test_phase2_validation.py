"""Unit checks for the Phase 2 collector's scope validation."""

import asyncio
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.browser import _Journey, _origin, _public_addresses, collect


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://merchant.test"
IP_ERROR = "authorize a domain name; IP-literal targets are not supported"


def validate_record(test, record):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "audit.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "skills/india-dpdp-audit/scripts/audit.py"), "validate", str(path)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
    test.assertEqual(result.returncode, 0, result.stderr)


class ScopeTests(unittest.TestCase):
    def test_origin(self):
        cases = (
            ("https://Merchant.test/contact", "https://merchant.test"),
            ("https://merchant.test:443/", "https://merchant.test"),
            ("https://user@merchant.test/", None),
            ("https://merchant.test:0/", None),
            ("https://merchant.test:65536/", None),
            ("https://merchant.test./", None),
            ("https://merchant.test\\path", None),
            ("https://127.000.000.001/", None),
            ("https://0x7f000001/", None),
            ("https://2130706433/", None),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                if expected is None:
                    with self.assertRaises(ValueError):
                        _origin(url)
                else:
                    self.assertEqual(_origin(url), expected)

    def test_literal_targets_are_refused_before_collection(self):
        with patch("collector.browser._collect") as run:
            for origin in ("https://1.1.1.1", "https://[2606:4700::1111]", "http://127.0.0.1:8123",
                           "https://[64:ff9b::7f00:1]", "https://100.64.0.1", "https://[fe80::1]"):
                options = {"authorization": {"attested": True, "interactions": []}}
                for target, authorized_origin, consent_url in (
                    (origin + "/", origin, None), (origin + "/", ORIGIN, None),
                    (ORIGIN + "/", ORIGIN, origin + "/"),
                ):
                    with self.subTest(target=target, consent=consent_url), self.assertRaisesRegex(ValueError, IP_ERROR):
                        collect(target, authorized_origin=authorized_origin, consent_url=consent_url, **options)
            run.assert_not_called()

    def test_authorization_must_attest_exact_actions_before_collection(self):
        origin = "https://merchant.test"
        actions = {"reject": "#reject"}
        cases = (
            None,
            {"attested": False, "interactions": ["reject"]},
            {"attested": 1, "interactions": ["reject"]},
            {"attested": True},
            {"attested": True, "interactions": []},
            {"attested": True, "interactions": ["accept"]},
            {"attested": True, "interactions": ["reject", "accept"]},
            {"attested": True, "interactions": ["reject", "reject"]},
            {"attested": True, "interactions": "reject"},
        )
        with patch("collector.browser._collect") as run:
            with self.assertRaises(TypeError):
                collect(origin, authorized_origin=origin, actions=actions)
            for authorization in cases:
                with self.subTest(authorization=authorization), self.assertRaises(ValueError):
                    collect(origin, authorized_origin=origin, authorization=authorization, actions=actions)
            run.assert_not_called()


class PublicAddressTests(unittest.IsolatedAsyncioTestCase):
    async def test_dns_answers_must_all_be_public(self):
        cases = (
            (("1.1.1.1", "1.1.1.1", "2606:4700::1111"), ("1.1.1.1", "2606:4700::1111")),
            (("64:ff9b::101:101",), ("64:ff9b::101:101",)),
            (("64:ff9b::c000:201",), None),
            (("1.1.1.1", "64:ff9b::7f00:1"), None),
            (("100.64.0.1",), None),
            (("fe80::1",), None),
            (("127.0.0.1",), None),
            (("ff02::1",), None),
            ((), None),
        )
        for addresses, expected in cases:
            answers = [(None, socket.SOCK_STREAM, None, "", (address, 0)) for address in addresses]
            lookup = AsyncMock(return_value=answers)
            with self.subTest(addresses=addresses), patch.object(asyncio.get_running_loop(), "getaddrinfo", lookup):
                if expected is None:
                    with self.assertRaisesRegex(OSError, "non-public resolution"):
                        await _public_addresses("https://merchant.test")
                else:
                    self.assertEqual(await _public_addresses("https://merchant.test"), expected)
                lookup.assert_awaited_once_with("merchant.test", None, type=socket.SOCK_STREAM)


class CollectorRecordTests(unittest.TestCase):
    def collect_record(self, capture):
        from collector.audit_record import build_audit_record

        with patch("collector.browser._collect", side_effect=capture):
            packet = collect(ORIGIN + "/", authorized_origin=ORIGIN,
                             authorization={"attested": True, "interactions": []})
        record = build_audit_record(packet)
        validate_record(self, record)
        return packet, record

    def test_missing_document_is_an_open_question_with_a_next_step(self):
        async def capture(packet, *_):
            initial = packet["observations"][0]
            initial.update(status="blocked", page_status=403, reasons=["document_unavailable"])

        packet, record = self.collect_record(capture)
        self.assertEqual(packet["observations"][0]["document_evidence_status"], "unknown")
        self.assertTrue(all(item["evidence_status"] == "not_verified" for item in record["findings"]))
        question = next(item for item in record["findings"] if "Initial consent page" in item["title"])
        self.assertIn("Could not verify", question["observation"])
        self.assertNotIn(question["priority"], {"high", "critical"})
        self.assertTrue(any(question["id"] in action["finding_ids"] and action["kind"] == "evidence_request"
                            for action in record["actions"]))
        owner = next(item for item in record["evidence"] if item["kind"] == "owner_statement")
        self.assertEqual(packet["authorization"]["evidence_status"], "supplied")
        self.assertEqual(owner["status"], "asserted")

    def test_observed_unlabeled_field_is_a_gap_even_with_partial_coverage(self):
        from merchant.report import render_summary

        async def capture(packet, *_):
            initial = packet["observations"][0]
            journey = _Journey(ORIGIN, (), (), 500, ())
            journey.page = AsyncMock()
            journey.page.context.cookies.return_value = []
            journey.read_document = AsyncMock(return_value={
                "empty": False, "truncated": False, "notices": [],
                "forms": [{"fields": [{"tag": "input", "type": "text", "missing_label": True}]}],
                "storage": {"local": 0, "session": 0},
            })
            await journey.snapshot(initial)
            initial.update(status="observed", requests=[{
                "resource_type": "script", "disposition": "observed", "status": 403, "reason": None,
                "attempt_evidence_status": "observed", "response_evidence_status": "observed",
            }, {
                "resource_type": "script", "disposition": "blocked", "status": None,
                "reason": "out_of_scope_origin", "attempt_evidence_status": "observed",
                "response_evidence_status": "unknown",
            }])
            journey.current = initial
            journey.finish_observation()

        packet, record = self.collect_record(capture)
        initial = packet["observations"][0]
        self.assertEqual(initial["document_evidence_status"], "observed")
        self.assertEqual(initial["status"], "partial")
        self.assertIn("resource_response_unavailable", initial["reasons"])
        self.assertEqual(next(item for item in record["findings"] if item["id"] == "F-initial")["evidence_status"],
                         "not_verified")
        gap, = [item for item in record["findings"] if item["evidence_status"] == "observed_gap"]
        evidence, = [item for item in record["evidence"] if item["id"] in gap["evidence_ids"]]
        self.assertEqual(evidence["status"], "direct")
        self.assertIn("without a label", evidence["observation"])
        self.assertEqual(gap["confidence"], "medium")
        self.assertIn("sampled while 1 page resource was blocked", gap["observation"])
        summary, usable = render_summary(packet, record)
        self.assertTrue(usable)
        self.assertLess(summary.index("## Observed gaps"), summary.index("## Open questions"))
        self.assertIn(f"Evidence `{evidence['id']}`", summary)
