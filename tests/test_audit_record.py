import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "india-dpdp-audit"
CLI = SKILL / "scripts" / "audit.py"
EXAMPLE = SKILL / "assets" / "example-audit.json"
spec = importlib.util.spec_from_file_location("audit", CLI)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = audit.schema_validator()

    def setUp(self):
        self.record = audit.read_json(EXAMPLE)

    def assertInvalid(self, expected):
        errors = audit.validate(self.record, self.validator)
        self.assertTrue(any(expected in error for error in errors), errors)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *map(str, args)],
            capture_output=True, text=True, check=False,
        )

    def test_example_roundtrip(self):
        self.assertEqual(audit.validate(self.record, self.validator), [])
        result = self.cli("validate", EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("render", EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        for marker in (
            "not verified", "not inspected", "blocked", "unknown",
            "Ticket deletion remains unverified", "Purpose of required phone collection",
            "Owner-asserted ground", "Preparation date", "Verification step", "Effort", "Target",
        ):
            self.assertIn(marker, result.stdout)

    def test_dangling_and_duplicate_references(self):
        self.record["actions"][0]["finding_ids"].append("F-missing")
        self.record["findings"][0]["evidence_ids"].append("E-missing")
        self.record["findings"][0]["legal_ids"].append("L-missing")
        self.record["coverage"][1]["id"] = self.record["evidence"][0]["id"]
        self.assertInvalid("unknown findings ID F-missing")
        self.assertInvalid("unknown evidence ID E-missing")
        self.assertInvalid("unknown legal_ledger ID L-missing")
        self.assertInvalid("duplicate ID E-form")

    def test_future_current_duty_is_rejected(self):
        self.record["legal_ledger"][0].update(status="current", effective_on="2027-05-13")
        self.record["findings"][0]["legal_status"] = "current"
        self.assertInvalid("current duty requires an effective date or latest commencement on or before the audit date")

    def test_current_duty_can_retain_exact_date_uncertainty(self):
        entry = self.record["legal_ledger"][0]
        entry.update(status="current", effective_by="2026-10-27")
        self.record["findings"][0]["legal_status"] = "current"
        self.assertEqual(audit.validate(self.record, self.validator), [])
        self.assertIn("Effective by (latest supported date)", audit.render(self.record))

        entry["effective_by"] = "2026-10-28"
        self.assertInvalid("latest commencement on or before the audit date")
        entry["effective_on"] = "2026-10-26"
        self.assertInvalid("effective_by is only valid when the exact effective date is unresolved")

    def test_future_label_rejected_after_latest_possible_commencement(self):
        self.record["legal_ledger"][0]["effective_by"] = "2026-10-26"
        self.assertInvalid("future duty has an effective date or latest commencement on or before the audit date")

    def test_finding_cannot_override_ledger_status(self):
        self.record["findings"][0]["legal_status"] = "current"
        self.assertInvalid("current requires ledger entries with the same status")

    def test_scope_does_not_allow_source_or_internal_verification(self):
        self.record["scope"]["modes"] = ["public"]
        del self.record["scope"]["authorized_repositories"]
        self.assertInvalid("repository_code requires repository scope")
        self.record["evidence"][1]["kind"] = "internal_record"
        self.assertInvalid("internal_record requires internal scope")

    def test_public_evidence_requires_exact_authorized_domain(self):
        self.record["evidence"][0]["locator"] = "https://support.example.test.attacker.test/contact"
        self.assertInvalid("authorized domain")
        self.record["evidence"][0]["locator"] = "https://elsewhere.test@support.example.test/contact"
        self.assertInvalid("authorized domain")

    def test_code_evidence_requires_authorized_revision(self):
        self.record["evidence"][1]["revision"] = "arbitrary-unreviewed-revision"
        self.assertInvalid("authorized repository and revision")

    def test_limited_and_asserted_evidence_do_not_confirm_failure(self):
        self.record["evidence"][0]["status"] = "limited"
        self.record["findings"][0]["evidence_ids"] = ["E-form", "E-owner"]
        self.assertInvalid("observed_gap requires direct evidence")
        self.record["findings"][0]["evidence_ids"] = []
        self.assertInvalid("observed_gap requires direct evidence")

    def test_code_cannot_substitute_for_owner_claim(self):
        self.record["data_map"][0]["owner_claims"][0]["evidence_ids"] = ["E-handler"]
        self.assertInvalid("owner claims require owner_statement evidence")

    def test_unverified_findings_generate_evidence_requests(self):
        self.record["actions"][1]["kind"] = "remediation"
        self.assertInvalid("not_verified findings require an evidence request")

    def test_gaps_and_unknowns_require_linked_actions(self):
        self.record["actions"].clear()
        self.assertInvalid("F-phone: observed_gap finding requires a linked action")
        self.assertInvalid("F-deletion: not_verified finding requires a linked action")

    def test_verified_action_requires_direct_evidence_in_matching_mode(self):
        action = self.record["actions"][1]
        action["verification_status"] = "verified"
        self.assertInvalid("requires direct verification evidence")
        action["verification_evidence_ids"] = ["E-form", "E-owner"]
        self.assertInvalid("requires direct verification evidence")

    def test_verified_action_needs_fresh_evidence_and_verified_dependencies(self):
        action = self.record["actions"][0]
        action.update(verification_status="verified", verification_evidence_ids=["E-form"])
        self.assertInvalid("verification must be newer than the baseline evidence")
        self.record["evidence"].append(dict(
            self.record["evidence"][0],
            id="E-recheck", captured_at="2026-10-27T11:00:00+05:30",
            observation="The form marked phone as optional on the authorized follow-up check.",
        ))
        action["verification_evidence_ids"] = ["E-recheck"]
        self.assertEqual(audit.validate(self.record, self.validator), [])
        action["dependencies"] = ["A-record"]
        self.assertInvalid("verified action has an unverified dependency")

    def test_action_cycles_are_rejected(self):
        self.record["actions"][0]["dependencies"] = ["A-record"]
        self.record["actions"][1]["dependencies"] = ["A-phone"]
        self.assertInvalid("action dependency cycle")

    def test_action_plan_requires_target_effort_and_verification_steps(self):
        action = self.record["actions"][0]
        del action["target"]
        del action["effort"]
        action["verification_steps"] = []
        self.assertInvalid("'target' is a required property")
        self.assertInvalid("'effort' is a required property")
        self.assertInvalid("verification_steps")

    def test_audit_cutoff_uses_india_calendar_date(self):
        self.record["evidence"][0]["captured_at"] = "2026-10-27T19:00:00Z"
        self.assertInvalid("evidence captured after the audit date")
        self.record["evidence"][0]["captured_at"] = "2026-10-28T01:00:00.1+09:00"
        self.assertEqual(audit.validate(self.record, self.validator), [])

    def test_dates_are_real_and_timezones_required(self):
        self.record["audit_date"] = "2026-02-31"
        self.assertInvalid("not a 'date'")
        self.record["evidence"][0]["captured_at"] = "2026-10-27T09:10:00"
        self.assertInvalid("not a 'date-time'")

    def test_invalid_json_does_not_render_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            for body, expected in (
                ("{", "Expecting"),
                ('{"a": 1, "a": 2}', "duplicate JSON member"),
                ('{"audit_date": NaN}', "invalid JSON constant"),
                ('{"schema_version": "invalid"}', "schema_version"),
            ):
                with self.subTest(body=body):
                    path.write_text(body, encoding="utf-8")
                    result = self.cli("render", path)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(expected, result.stderr)

    def test_untrusted_markdown_is_rendered_as_text(self):
        payload = "# Title\n- item\n[click](javascript:alert(1)) <img src=x onerror=x> ![x](https://x.test) &lt;b&gt; `code`\x1b[31m"
        self.record["findings"][0]["title"] = payload
        self.record["evidence"][0]["observation"] = payload
        self.assertEqual(audit.validate(self.record, self.validator), [])
        rendered = audit.render(self.record)
        for raw in ("\n# Title", "\n- item", "[click](", "<img", "![x](", "&lt;b&gt;", "`code`", "\x1b"):
            with self.subTest(raw=raw):
                self.assertNotIn(raw, rendered)
        self.assertIn("&#60;img", rendered)
        self.assertIn("&#91;click&#93;", rendered)

    def test_diff_validates_both_inputs_and_reports_changes_by_id(self):
        with tempfile.TemporaryDirectory() as directory:
            later = Path(directory) / "later.json"
            self.record["coverage"].reverse()
            self.record["findings"][0]["confidence"] = "medium"
            self.record["findings"].pop()
            self.record["actions"].pop()
            later.write_text(json.dumps(self.record), encoding="utf-8")
            result = self.cli("diff", EXAMPLE, later)
            self.assertEqual(result.returncode, 0, result.stderr)
            changes = json.loads(result.stdout)
            self.assertNotIn("coverage", changes)
            self.assertEqual(changes["findings"]["changed"], {"F-phone": ["confidence"]})
            self.assertEqual(changes["findings"]["removed"], ["F-deletion"])
            self.assertEqual(changes["actions"]["removed"], ["A-record"])
            later.write_text("{}", encoding="utf-8")
            result = self.cli("diff", EXAMPLE, later)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
