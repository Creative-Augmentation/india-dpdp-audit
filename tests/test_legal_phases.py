from datetime import date
import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "skills/india-dpdp-audit/scripts/legal_phases.py"
SPEC = importlib.util.spec_from_file_location("legal_phases", MODULE)
legal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legal)


class LegalPhaseTests(unittest.TestCase):
    def entry(self, provision, status="current", instrument="DPDP Rules, 2025", **dates):
        return {
            "id": "L-001", "instrument": instrument, "provision": provision,
            "status": status, "effective_on": None, **dates,
        }

    def test_rules_mixed_phase_list_cannot_assert_current(self):
        e = self.entry("Rules 1 and 3", effective_by="2026-10-27")
        self.assertIn("spans multiple", legal.check_entry(e, "2026-10-27")[0])
        self.assertEqual(legal.check_entry(self.entry("Rules 1 and 3", "uncertain"), "2026-10-27"), [])

    def test_later_rule_cannot_use_immediate_date(self):
        e = self.entry("Rule 3", effective_on="2025-11-13")
        errors = legal.check_entry(e, "2026-10-27")
        self.assertTrue(any("contradicts pinned" in error for error in errors))
        self.assertTrue(any("cannot be current" in error for error in errors))

    def test_later_rule_cannot_be_future_after_latest_without_input_dates(self):
        e = self.entry("Rule 3", "future")
        self.assertIn("cannot be future", legal.check_entry(e, "2027-05-14")[0])
        self.assertEqual(legal.check_entry(e, "2027-05-12"), [])

    def test_all_three_boundary_days_preserve_uncertainty(self):
        for provision, earliest, latest in (
            ("Rule 1", "2025-11-13", "2025-11-14"),
            ("Rule 4", "2026-11-13", "2026-11-14"),
            ("Rule 3", "2027-05-13", "2027-05-14"),
        ):
            with self.subTest(provision=provision):
                for status in ("current", "future"):
                    e = self.entry(provision, status, effective_on=earliest)
                    self.assertIn("uncertain on the audit date", legal.check_entry(e, earliest)[0])
                e = self.entry(provision, effective_by=latest)
                self.assertEqual(legal.check_entry(e, date.fromisoformat(latest)), [])
                e["effective_by"] = earliest
                self.assertIn("must equal pinned", legal.check_entry(e, latest)[0])

    def test_act_phase_exceptions_and_whole_section_ambiguity(self):
        for provision, latest in (
            ("Section 1(2)", "2025-11-14"),
            ("Sections 18–26, 35 and 38 to 43", "2025-11-14"),
            ("Sections 44(1) and 44(3)", "2025-11-14"),
            ("Sections 6(9), 27(1)(d)", "2026-11-14"),
            ("Sections 3–5, 6(8), 6(10) and 7-17", "2027-05-14"),
            ("Sections 27(1)(a), 27(2), 27(3) and 44(2)", "2027-05-14"),
        ):
            with self.subTest(provision=provision):
                e = self.entry(provision, instrument="Digital Personal Data Protection Act, 2023",
                               effective_by=latest)
                self.assertEqual(legal.check_entry(e, latest), [])
                self.assertEqual(legal.entry_warnings(e), [])
        for provision in ("Sections 6", "Section 27", "Section 27(1)", "Section 44"):
            e = self.entry(provision, instrument="DPDP Act 2023")
            self.assertIn("spans multiple", legal.check_entry(e, "2027-05-14")[0])

    def test_unmapped_citations_warn_and_uncertain_is_accepted(self):
        for provision in ("Section 1", "Section 1(1)", "Section 27(8)", "Section 1(2) and Schedule II"):
            with self.subTest(provision=provision):
                e = self.entry(provision, "uncertain", instrument="DPDP Act 2023")
                self.assertIn("unmapped", legal.entry_warnings(e)[0])
                self.assertEqual(legal.check_entry(e, "2027-05-14"), [])
                e["status"] = "current"
                self.assertIn("unmapped", legal.check_entry(e, "2027-05-14")[0])

    def test_descriptive_prose_and_draft_rules_are_unmapped(self):
        for instrument, provision in (
            ("DPDP Rules 2025", "Rule 1 (commencement) and rule 3 for notice"),
            ("Draft DPDP Rules 2025", "Rule 3"),
        ):
            e = self.entry(provision, instrument=instrument)
            self.assertIn("unmapped", legal.check_entry(e, "2026-10-27")[0])

    def test_number_alone_uses_identified_dpdp_instrument(self):
        e = self.entry("3", instrument="G.S.R. 846(E), final rules")
        self.assertIn("cannot be current", legal.check_entry(e, "2026-10-27")[0])
        e = self.entry("3", instrument="Gazette notification",
                       source_url=(
                           "https://www.meity.gov.in/static/uploads/2025/11/"
                           "53450e6e5dc0bfa85ebd78686cadad39.pdf"
                       ))
        self.assertIn("cannot be current", legal.check_entry(e, "2026-10-27")[0])

    def test_other_instruments_keep_existing_validation(self):
        e = self.entry("Rule 3", instrument="Unrelated Law")
        self.assertEqual(legal.entry_warnings(e), [])
        self.assertEqual(legal.check_entry(e, "2026-10-27"), [])


if __name__ == "__main__":
    unittest.main()
