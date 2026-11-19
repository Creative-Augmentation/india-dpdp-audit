import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

try:
    from cmarkgfm import github_flavored_markdown_to_html
except ImportError as error:
    raise ImportError("Install the renderer test dependency with pip install -r tests/requirements.txt") from error

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
        entry.update(
            instrument="Final DPDP Rules 2025, G.S.R. 846(E)",
            provision="Rule 1",
            status="current",
            effective_by="2025-11-14",
        )
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

    def test_ledger_validation_checks_pinned_dpdp_phase(self):
        entry = self.record["legal_ledger"][0]
        entry.update(
            provision="Rules 1 and 3",
            status="current",
            effective_on="2025-11-14",
        )
        self.record["findings"][0]["legal_status"] = "current"
        self.assertInvalid("spans multiple DPDP commencement phases")
        entry.update(provision="Rule 3", status="future", effective_on=None, verified_on="2027-05-15")
        self.record["findings"][0]["legal_status"] = "future"
        self.record["audit_date"] = "2027-05-15"
        self.assertInvalid("L-notice: DPDP provision cannot be future")

    def test_legal_phase_warnings_in_validate_and_report(self):
        entry = self.record["legal_ledger"][0]
        entry.update(instrument="The Rules, 2025", status="uncertain",
                     source_url="https://www.example-lawblog.test/india/rules-2025.pdf")
        self.record["findings"][0]["legal_status"] = "uncertain"
        self.record["legal_ledger"].append(dict(entry, id="L-opaque"))
        warning, = audit.legal_phases.entry_warnings(entry, self.record["audit_date"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(json.dumps(self.record), encoding="utf-8")
            result = self.cli("validate", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "Audit record is valid.\n")
            self.assertIn(warning, result.stderr)
            self.assertIn("L-opaque", result.stderr)

        report = audit.render(self.record)
        self.assertIn("**Legal phase warnings** · 2", report.split("## Scope", 1)[0])
        self.assertIn("**Source** ` https://www.example-lawblog.test/india/rules-2025.pdf ` "
                      "(not in pinned official registry)", report)
        self.assertIn("**Legal phase review**", report)
        self.assertNotIn("**Official source**", report)

    def test_future_duty_requires_a_commencement_or_preparation_date(self):
        entry = self.record["legal_ledger"][0]
        entry.pop("preparation_on")
        self.assertIsNone(entry["effective_on"])
        self.assertInvalid("future duty requires effective_on, effective_by, or preparation_on")

    def test_future_duty_requires_reverification_after_preparation_date(self):
        entry = self.record["legal_ledger"][0]
        entry.update(
            instrument="Synthetic duty",
            source_url="https://gazette.example.test/synthetic-duty",
            provision="Clause A",
            preparation_on="2026-10-26",
            verified_on="2026-10-26",
        )
        self.assertInvalid("future duty is past the preparation date")
        entry["verified_on"] = "2026-10-27"
        self.assertEqual(audit.validate(self.record, self.validator), [])

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

    def test_success_and_exclusion_reject_owner_or_limited_evidence_padding(self):
        finding = self.record["findings"][0]
        limited = dict(self.record["evidence"][0], id="E-limited", status="limited")
        self.record["evidence"].append(limited)
        for status, applicability in (
            ("meets_sampled_check", "unknown"), ("not_applicable", "not_applicable"),
        ):
            for evidence_ids in (["E-form", "E-owner"], ["E-form", "E-limited"], []):
                with self.subTest(status=status, evidence_ids=evidence_ids):
                    finding.update(evidence_status=status, applicability=applicability, evidence_ids=evidence_ids)
                    self.assertInvalid(f"{status} requires only direct non-owner evidence")

    def test_success_and_exclusion_require_all_evidence_in_india_audit_window(self):
        finding = self.record["findings"][0]
        finding["evidence_ids"] = ["E-form", "E-handler"]
        self.record["evidence"][0]["captured_at"] = "2026-10-26T18:29:59Z"
        for status, applicability in (
            ("meets_sampled_check", "unknown"), ("not_applicable", "not_applicable"),
        ):
            with self.subTest(status=status):
                finding.update(evidence_status=status, applicability=applicability)
                self.record["scope"].pop("audit_window_start", None)
                self.assertInvalid(f"{status} requires evidence captured in the audit window")
                self.record["scope"]["audit_window_start"] = "2026-10-26"
                self.assertEqual(audit.validate(self.record, self.validator), [])
        self.record["scope"]["audit_window_start"] = "2026-10-28"
        self.assertInvalid("scope.audit_window_start is after the audit date")

    def test_default_window_limit_and_extended_reason(self):
        self.record["scope"]["audit_window_start"] = "2026-09-27"
        self.assertEqual(audit.validate(self.record, self.validator), [])
        self.record["scope"]["audit_window_start"] = "2026-09-26"
        self.assertInvalid("scope.audit_window_reason is required")
        for reason in ("   ", "x", ".", "\u200b", "o\u200bn\u200bl\u200by a word", "repeat " * 6):
            with self.subTest(reason=reason):
                self.record["scope"]["audit_window_reason"] = reason
                self.assertInvalid("audit_window_reason")
        self.record["scope"]["audit_window_reason"] = "Two scheduled rounds of evidence gathering"
        self.assertIn("Audit window 2026-09-26 through 2026-10-27", self.summary())
        self.assertIn("**Extended audit window** · Two scheduled rounds", self.summary())

    def test_historical_gap_remains_visible_when_retesting_is_pending(self):
        self.record["audit_date"] = "2027-04-27"
        summary = self.summary()
        self.assertIn("Audit window 2027-04-27 through 2027-04-27", summary)
        self.assertIn("Oldest linked evidence date 2026-10-27", summary)
        self.assertIn("Purpose of required phone collection", summary)
        self.record["findings"][0]["evidence_status"] = "meets_sampled_check"
        self.assertInvalid("meets_sampled_check requires evidence captured in the audit window")
        self.record["scope"]["audit_window_start"] = "2026-10-27"
        self.assertInvalid("scope.audit_window_reason is required")
        self.record["scope"]["audit_window_reason"] = "Approved review of two storefront versions"
        self.assertIn("**Extended audit window**", self.summary())

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

    def test_missing_date_time_format_checker_has_install_hint(self):
        checkers = audit.Draft202012Validator.FORMAT_CHECKER.checkers
        with patch.dict(checkers):
            del checkers["date-time"]
            with self.assertRaisesRegex(ValueError, "Install.*scripts/requirements.txt"):
                audit.schema_validator()

    def test_capture_parser_rejects_naive_values_when_schema_is_bypassed(self):
        self.record["evidence"][0]["captured_at"] = "2026-10-27T09:10:00"
        errors = audit.check_consistency(self.record)
        self.assertIn("E-form.captured_at: captured_at requires a time zone offset", errors)

    def test_cli_accepts_bom_and_names_malformed_second_diff_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "followup.json"
            path.write_text(json.dumps(self.record), encoding="utf-8-sig")
            result = self.cli("diff", EXAMPLE, path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
            path.write_text("{", encoding="utf-8-sig")
            result = self.cli("diff", EXAMPLE, path)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn(f"{path}: Expecting", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

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

    def summary(self):
        self.assertEqual(audit.validate(self.record, self.validator), [])
        return audit.render(self.record).split("## Scope", 1)[0]

    def test_summary_leads_with_gap_and_concrete_actions(self):
        summary = self.summary()
        headings = ("Observed gaps", "Could not check", "Sampled successes", "Scope and coverage", "Next actions")
        positions = [summary.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("future duty, applicability unknown", summary)
        self.assertIn("Confirm why support needs the phone field", summary)
        self.assertIn("Request the retention policy", summary)
        self.assertIn("Inspected 1 of 3 recorded journeys (1 blocked, 1 uninspected)", summary)

    def test_detailed_findings_sort_evidence_status_before_priority(self):
        self.record["findings"].insert(0, dict(
            self.record["findings"][0],
            id="F-success",
            evidence_status="meets_sampled_check",
            priority="high",
            title="Support form explains how support uses email",
        ))
        self.assertEqual(audit.validate(self.record, self.validator), [])
        details = audit.render(self.record).split("## Findings", 1)[1]
        self.assertLess(
            details.index("Purpose of required phone collection"),
            details.index("Support form explains how support uses email"),
        )

    def test_empty_coverage_marks_missing_journey_evidence(self):
        for section in ("coverage", "evidence", "data_map", "legal_ledger", "findings", "actions"):
            self.record[section].clear()
        summary = self.summary()
        self.assertIn("No journeys were recorded", summary)
        self.assertIn("not legal advice or a compliance certificate", summary)
        self.assertIn(
            "No findings were recorded. See the summary for journey coverage and evidence limits.",
            audit.render(self.record),
        )
        self.assertIn("List the collection and data", summary)
        self.assertIn("Overall compliance remains undetermined", summary)

    def test_no_findings_with_blocked_and_uninspected_journeys(self):
        self.record["findings"].clear()
        self.record["actions"].clear()
        self.record["data_map"].clear()
        self.record["coverage"].pop(0)
        summary = self.summary()
        self.assertIn("The record shows no completed journey inspections", summary)
        self.assertIn("Shopify checkout (blocked)", summary)
        self.assertIn("Downstream retention and deletion (not inspected)", summary)
        self.assertIn("finish the 2 outstanding journey inspections", summary)
        self.assertIn("Overall compliance remains undetermined", summary)

    def test_only_unverified_findings_are_reported_as_could_not_check(self):
        self.record["findings"].pop(0)
        self.record["actions"].pop(0)
        summary = self.summary()
        self.assertIn("Ticket deletion remains unverified", summary)
        self.assertIn("Request the retention policy", summary)
        self.assertIn("Overall compliance remains undetermined", summary)

    def test_completed_sample_with_success_cannot_establish_overall_compliance(self):
        self.record["coverage"] = self.record["coverage"][:1]
        self.record["findings"] = self.record["findings"][:1]
        self.record["findings"][0].update(
            evidence_status="meets_sampled_check",
            title="Support form explains how support uses email",
        )
        self.record["actions"].clear()
        summary = self.summary()
        self.assertIn("Support form explains how support uses email", summary)
        self.assertIn("**Sampled successes** · 1 recorded check.", summary)
        self.assertIn("Inspected 1 of 1 recorded journeys", summary)
        self.assertIn("Overall compliance remains undetermined", summary)
        self.record["summary"] = "Compliant"
        self.assertInvalid("Additional properties")

    def test_summary_caps_previews_and_preserves_detailed_findings(self):
        for index in range(6):
            self.record["findings"].append({
                **self.record["findings"][0],
                "id": f"F-extra{index}",
                "title": f"Extra finding {index} " + "word " * 60,
            })
            self.record["actions"][0]["finding_ids"].append(f"F-extra{index}")
        summary = self.summary()
        self.assertIn("4 more in the detailed report", summary)
        self.assertNotIn("Extra finding 5", summary)
        self.assertNotIn("word " * 60, summary)
        self.assertIn("Extra finding 5 " + "word " * 59, audit.render(self.record))

    def test_untrusted_markdown_is_rendered_as_text(self):
        payload = "# Title\n- item\n[click](javascript:alert(1)) <img src=x onerror=x> ![x](https://x.test) &lt;b&gt; `code`\x1b[31m"
        self.record["findings"][0]["title"] = payload
        self.record["evidence"][0]["observation"] = payload
        self.assertEqual(audit.validate(self.record, self.validator), [])
        rendered = audit.render(self.record)
        for raw in ("\n# Title", "\n- item", "[click](", "<img", "&lt;b&gt;", "`code`", "\x1b"):
            with self.subTest(raw=raw):
                self.assertNotIn(raw, rendered)
        self.assertIn("&#60;img", rendered)
        self.assertIn("&#91;click&#93;", rendered)
        self.assertIn("&#91;click&#93;", self.summary())

    def test_markdown_preserves_indic_combining_marks_joiners_and_punctuation(self):
        text = "गोपनीयता, क्\u200dष क्\u200cष (सूचना)।"
        self.assertEqual(audit.markdown(text), text)
        self.assertEqual(audit.markdown("safe\u202e\u2067\x00\x85field"), "safefield")


    def test_gfm_keeps_links_and_raw_markup_inert_throughout_report(self):
        payload = (
            "गोपनीयता क्\u200dष क्\u200cष merchant@example.test mailto:merchant@example.test "
            "xmpp:merchant@example.test ftp://example.test www.example.test https://example.test "
            "https://example.test/```![x](https://example.test) <a href='https://example.test'>test</a> "
            "[click](https://example.test) <img src=x onerror=x>"
        )
        self.record["findings"][0]["title"] = payload
        self.record["evidence"][0]["observation"] = payload
        self.record["scope"]["subject"] = payload
        rendered = github_flavored_markdown_to_html(audit.render(self.record))
        for markup in ("<a ", "<img ", "<script", "<pre>", "<!-- raw HTML omitted -->"):
            with self.subTest(markup=markup):
                self.assertNotIn(markup, rendered)
        self.assertIn("गोपनीयता क्\u200dष क्\u200cष", rendered)
        for literal in ("merchant@example.test", "mailto:merchant@example.test",
                        "xmpp:merchant@example.test", "ftp://example.test"):
            self.assertIn(f"<code>{literal}</code>", rendered)

    def test_diff_warns_when_scope_changes_and_ignores_reference_order(self):
        before = deepcopy(self.record)
        self.record["findings"][0]["evidence_ids"].reverse()
        self.record["scope"]["authorized_domains"].reverse()
        self.assertEqual(audit.diff(before, self.record), {})
        self.record["scope"]["subject"] = "Different storefront"
        changes = audit.diff(before, self.record)
        self.assertEqual(changes["scope"], ["subject"])
        self.assertIn("comparable", changes["scope_warnings"][0])

    def test_diff_status_upgrade_requires_new_linked_direct_evidence(self):
        before = deepcopy(self.record)
        finding = self.record["findings"][0]
        finding["evidence_status"] = "meets_sampled_check"
        self.assertIn("F-phone:", audit.diff(before, self.record)["closure_warnings"][0])

        self.record["audit_date"] = "2026-10-28"
        self.record["scope"]["audit_window_start"] = "2026-10-27"
        fresh = dict(self.record["evidence"][0], id="E-recheck", captured_at="2026-10-28T00:30:00+05:30")
        self.record["evidence"].append(fresh)
        self.assertIn("closure_warnings", audit.diff(before, self.record))
        finding["evidence_ids"] = ["E-recheck"]
        self.assertEqual(audit.validate(self.record, self.validator), [])
        warnings = audit.diff(before, self.record)["closure_warnings"]
        self.assertIn("repeats an earlier kind, locator and observation", warnings[0])
        fresh["observation"] = "The follow-up form explains the optional phone collection."
        self.assertNotIn("closure_warnings", audit.diff(before, self.record))

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
            self.assertIn("F-deletion: removed finding", changes["closure_warnings"][0])
            self.assertEqual(changes["actions"]["removed"], ["A-record"])
            later.write_text("{}", encoding="utf-8")
            result = self.cli("diff", EXAMPLE, later)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
