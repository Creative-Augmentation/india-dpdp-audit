from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checks.audit_bridge import build_audit_record
from checks.contract import Basis, Check, CheckResult, Need
from checks.evidence import EvidenceBundle, MAX_FILE_BYTES
from checks.registry import register, run_checks
from checks.retest import retest
from checks.stacks import detect_stacks
from tests.test_checks_contract import demo_check


def packet(status="observed", **fields):
    return {
        "authorized_origin": "https://shop.example.test",
        "finished_at": "2026-11-23T11:00:00+00:00",
        "observations": [{"phase": "initial", "status": status, **fields}],
    }


class RunnerTests(unittest.TestCase):
    def setUp(self):
        registry = patch("checks.registry._CHECKS", {})
        registry.start()
        self.addCleanup(registry.stop)

    def test_absent_or_incomplete_evidence_prevents_decision(self):
        need = Need("packet", "initial", "/forms")
        check = Check("GEN-TEST", "generic", "Sample forms", Basis("good_practice", note="Inspect forms."),
                      (need,), lambda evidence: CheckResult("ok", "Forms sampled.", ("packet:/observations/0/forms",)))
        for bundle in (
            EvidenceBundle(),
            EvidenceBundle(packet()),
            EvidenceBundle(packet(forms=[], document_evidence_status="unknown")),
            *(EvidenceBundle(packet(status, forms=[])) for status in ("blocked", "partial", "not_attempted")),
        ):
            with self.subTest(bundle=bundle.packet):
                result = check.run(bundle)
                self.assertEqual(result.status, "could_not_check")
                self.assertIn("initial", result.missing[0])
                self.assertTrue(result.evidence_request)
        self.assertEqual(check.run(EvidenceBundle(packet(forms=[], document_evidence_status="observed"))).status, "ok")

    def test_resolution_and_read_only_local_loading(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "packet.json").write_text(json.dumps(packet(forms=[{"a/b~": None}])))
            (root / "config.json").write_text('{"items": [false]}')
            (root / "settings.toml").write_text("[settings]\nenabled = true\n")
            (root / "case.json").write_text('{"expect": "ok"}')
            bundle = EvidenceBundle.from_directory(root)
            self.assertEqual(bundle.artifact_names, ("config.json", "settings.toml"))
            self.assertIs(bundle.resolve(bundle.artifact_ref("config.json", "items", 0)), False)
            ref = bundle.packet_ref(0, "forms", 0, "a/b~")
            self.assertEqual(ref, "packet:/observations/0/forms/0/a~1b~0")
            self.assertTrue(bundle.resolves(ref))
            self.assertIsNone(bundle.resolve(ref))
            self.assertEqual(bundle.resolve(bundle.line_ref("settings.toml", 1, 2)),
                             "[settings]\nenabled = true")
            for invalid in ("packet:/observations/-1", "packet:/observations/00",
                            "packet:/observations/0/forms/0/a~2b",
                            "artifact:settings.toml#L1-L3", "artifact:../config.json:/items",
                            "artifact:config.json:/items/01", "artifact:config.json:/missing"):
                self.assertFalse(bundle.resolves(invalid), invalid)
            artifact = root / "config.json"
            artifact.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
            with self.assertRaises(ValueError):
                EvidenceBundle.from_directory(root)
            artifact.unlink()
            artifact.symlink_to(root / "settings.toml")
            with self.assertRaises(ValueError):
                EvidenceBundle.from_directory(root)

    def test_mixed_stack_detection_uses_only_retained_fields_and_artifact_markers(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "shopify.app.toml").write_text('name = "Demo"')
            supplied = root / "browser.json"
            supplied.write_text(json.dumps(packet(requests=[
                {"path": "/wp-content/plugins/woocommerce/style.css", "attempt_evidence_status": "observed"},
                {"path": None, "host": "unrecorded.myshopify.com"},
            ])))
            evidence = EvidenceBundle.from_directory(root, packet_path=supplied)
            detected = detect_stacks(evidence)
            self.assertEqual([entry.stack for entry in detected], ["shopify", "woocommerce"])
            for entry in detected:
                self.assertTrue(entry.confidence and entry.signals)
                self.assertTrue(all(evidence.resolves(ref) for ref in entry.signals))
        unknown = EvidenceBundle(packet(requests=[{"path": None, "host": "unrecorded.myshopify.com"}]))
        self.assertEqual([entry.stack for entry in detect_stacks(unknown)], ["generic"])

    def test_stable_selection_bad_results_and_exceptions(self):
        demo = demo_check()

        def broken(evidence):
            raise RuntimeError("untrusted exception text")

        def dangling(evidence):
            return CheckResult("ok", "Missing reference.", ("artifact:absent.json:/value",))

        for check in (replace(demo, id="Z-BROKEN", needs=(), evaluate=broken),
                      replace(demo, id="A-DANGLING", needs=(), evaluate=dangling),
                      replace(demo, id="S-SHOP", stack="shopify")):
            register(check)
        outcomes = run_checks(EvidenceBundle())
        self.assertEqual([row.check.id for row in outcomes], ["A-DANGLING", "Z-BROKEN"])
        self.assertEqual([row.result.status for row in outcomes], ["could_not_check"] * 2)
        self.assertNotIn("untrusted exception text", repr(outcomes))
        self.assertEqual([row.check.id for row in run_checks(EvidenceBundle(), ["shopify"])], ["S-SHOP"])
        with self.assertRaises(ValueError):
            register(outcomes[0].check)

    def test_retest_requires_a_new_resolvable_reference(self):
        check = demo_check()
        fixture = ROOT / "tests" / "check_fixtures" / "generic" / check.id
        failing = EvidenceBundle.from_directory(fixture / "positive")
        passing = EvidenceBundle.from_directory(fixture / "negative")
        previous = check.run(failing)
        self.assertEqual(retest(check, previous, failing), "still_failing")
        self.assertEqual(retest(check, previous, EvidenceBundle()), "could_not_check")
        self.assertEqual(retest(check, previous, passing), "could_not_check")
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "recollected.json").write_text('{"descriptive": true}')
            (root / "labels.json").write_text('{"descriptive": true}')
            fresh = EvidenceBundle.from_directory(root)
            updated = replace(check, evaluate=lambda bundle: CheckResult(
                "ok", "Recollected label is descriptive.", ("artifact:recollected.json:/descriptive",)))
            self.assertEqual(retest(updated, previous, fresh), "closed")

    def test_bridge_validates_for_all_outcomes_and_preserves_rule_basis(self):
        demo = demo_check()
        check = replace(demo, id="GEN-RULE", title="Observed initial form",
                        basis=Basis("legal", citation="Rule 3"),
                        needs=(Need("packet", "initial", "/forms"),),
                        evaluate=lambda bundle: CheckResult(
                            "ok", "The sample includes a form.", ("packet:/observations/0/forms/0",)))
        register(check)
        register(demo)
        register(replace(demo, id="GEN-UNAVAILABLE", needs=(Need("artifact", "missing.json"),)))
        fixture = ROOT / "tests" / "check_fixtures" / "generic" / demo.id / "positive"
        with TemporaryDirectory() as folder:
            root = Path(folder)
            packet_path = root / "browser.json"
            packet_path.write_text(json.dumps(packet(forms=[{"visible": True}],
                                                     document_evidence_status="observed")))
            evidence = EvidenceBundle.from_directory(fixture, packet_path=packet_path)
            record = build_audit_record(evidence, run_checks(evidence))
            self.assertEqual([row["evidence_status"] for row in record["findings"]], ["observed_gap", "not_verified"])
            self.assertEqual([row["kind"] for row in record["actions"]], ["remediation", "evidence_request"])
            self.assertIn("inspected", {row["status"] for row in record["coverage"]})
            self.assertEqual(record["legal_ledger"][0]["provision"], "Rule 3")
            output = root / "audit.json"
            output.write_text(json.dumps(record))
            validation = subprocess.run(
                [sys.executable, str(ROOT / "skills/india-dpdp-audit/scripts/audit.py"), "validate", str(output)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

    def test_cli_lists_and_runs_as_json(self):
        with TemporaryDirectory() as folder:
            for args in (["list"], ["run", folder]):
                process = subprocess.run([sys.executable, "-m", "checks", *args], cwd=ROOT,
                                         text=True, capture_output=True, check=True)
                self.assertIsInstance(json.loads(process.stdout), list)


if __name__ == "__main__":
    unittest.main()
