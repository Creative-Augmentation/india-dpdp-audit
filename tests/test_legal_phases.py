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

    def test_act_aliases_cannot_bypass_known_act_phases(self):
        for instrument in (
            "DPDPA2023",
            "Act No.22 of2023",
            "Data Protection Act2023",
            "डिजिटल वैयक्तिक डेटा संरक्षण अधिनियम, २०२३",
        ):
            with self.subTest(instrument=instrument):
                e = self.entry("Section 5", instrument=instrument, effective_on="2025-11-13")
                self.assertIn("contradicts pinned", legal.check_entry(e, "2026-10-27")[0])
        e = self.entry("धारा ५", instrument="डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023")
        self.assertIn("cannot be current", legal.check_entry(e, "2026-10-27")[0])

    def test_rules_of_act_and_hindi_rules_are_classified_as_rules(self):
        for instrument, provision in (
            ("Rules of the Digital Personal Data Protection Act, 2023", "Rules 1 and 3"),
            ("डिजिटल वैयक्तिक डेटा संरक्षण नियमावली, २०२५", "नियम १ और ३"),
            ("DPDPR2025", "Rules 1 and 3"),
            ("डिजिटल व्यक्तिगत डाटा संरक्षण नियमावली, 2025", "नियम १ और ३"),
        ):
            with self.subTest(instrument=instrument):
                e = self.entry(provision, instrument=instrument)
                self.assertIn("spans multiple", legal.check_entry(e, "2026-10-27")[0])

    def test_source_aliases_cover_operative_baseline_documents(self):
        baseline = MODULE.parents[1] / "references/legal-baseline.md"
        source_urls = {
            link.split("](", 1)[0]: link.split("](", 1)[1].split(")", 1)[0]
            for line in baseline.read_text(encoding="utf-8").splitlines()
            for link in line.split("[")[1:]
            if "](https://" in link
        }
        for title, provision in (
            ("DPDP Act 2023, official copy", "Section 5"),
            ("G.S.R. 843(E), commencement", "Section 5"),
            ("Final DPDP Rules 2025, G.S.R. 846(E)", "Rule 3"),
            ("G.S.R. 892(E), corrigenda", "Rule 3"),
            ("Official S.O. 5458(E)", "Section 9(1)"),
        ):
            source_url = source_urls[title] + "?test=1#page=1"
            with self.subTest(title=title):
                e = self.entry(provision, instrument="Government publication", source_url=source_url)
                self.assertIn("cannot be current", legal.check_entry(e, "2026-10-27")[0])
        for title in ("PIB, 16 May 2026", "January 2026 MeitY upload"):
            e = self.entry("Rule 3", "uncertain", instrument="Government backgrounder",
                           source_url=source_urls[title])
            self.assertEqual(legal.check_entry(e, "2026-10-27"), [])
            warning = legal.entry_warnings(e)[0]
            self.assertNotIn("DPDP commencement", warning)

    def test_dpdp_like_unknown_official_citation_requires_uncertainty(self):
        e = self.entry(
            "not a canonical provision", instrument="Government publication",
            source_url="https://www.meity.gov.in/dpdp-related-unknown-document",
        )
        self.assertIn("unmapped", legal.check_entry(e, "2026-10-27")[0])
        e["status"] = "uncertain"
        self.assertEqual(legal.check_entry(e, "2026-10-27"), [])
        self.assertIn("unmapped", legal.entry_warnings(e)[0])

    def test_mapped_post_latest_uncertainty_requires_explanation_and_warns(self):
        e = self.entry("Rule 3", "uncertain", notes="Pending verification")
        self.assertIn("notes explaining", legal.check_entry(e, "2027-05-14")[0])
        e["notes"] = "The relevant Gazette notification remains inaccessible for this assessment."
        self.assertEqual(legal.check_entry(e, "2027-05-14"), [])
        self.assertIn("after the pinned latest", legal.entry_warnings(e, "2027-05-14")[0])
        self.assertEqual(legal.entry_warnings(e, "2027-05-13"), [])

    def test_opaque_official_source_requires_explicit_instrument(self):
        for host in ("www.meity.gov.in", "egazette.gov.in", "egazette.nic.in", "www.indiacode.nic.in"):
            e = self.entry("Section 5", instrument="Government publication",
                           source_url=f"https://{host}/opaque-a97d9.pdf")
            with self.subTest(host=host):
                self.assertIn("Cannot identify the instrument", legal.check_entry(e, "2026-10-27")[0])
                e["status"] = "uncertain"
                self.assertEqual(legal.check_entry(e, "2026-10-27"), [])
                self.assertIn("Cannot identify the instrument", legal.entry_warnings(e)[0])

    def test_short_instrument_aliases_apply_pinned_phases(self):
        for instrument, provision in (
            ("Data Protection Rules, 2025", "Rule 3"),
            ("Personal Data Protection Rules 2025", "Rule 3"),
            ("Data Protection Rules", "Rule 3"),
            ("Data Protection Act", "Section 8(7)"),
        ):
            with self.subTest(instrument=instrument):
                e = self.entry(provision, instrument=instrument, effective_on="2025-11-13",
                               source_url="https://www.example-lawblog.test/india/rules-2025.pdf")
                self.assertIn("cannot be current", "\n".join(legal.check_entry(e, "2026-10-27")))

    def test_opaque_pib_and_legacy_meity_citations_require_uncertainty(self):
        for source_url in (
            "https://pib.gov.in/PressReleasePage.aspx?PRID=2261823",
            "https://meity.nic.in/content/rules",
            "https://www.pib.nic.in/opaque.pdf",
        ):
            with self.subTest(source_url=source_url):
                e = self.entry("Rule 3", instrument="Notification of 13 November 2025",
                               effective_on="2025-11-13", source_url=source_url)
                self.assertIn("Cannot identify the instrument from the official citation",
                              legal.check_entry(e, "2026-10-27")[0])

    def test_format_characters_and_confusables_in_aliases_apply_pinned_phases(self):
        for instrument in (
            "D\u200bPDP Rules 2025",
            "DP\u00adDP Rules 2025",
            "Digital Personal Data Pro\u00adtection Rules, 2025",
            "ДPDP Rules 2025",
        ):
            with self.subTest(instrument=instrument):
                e = self.entry("Rule 3", instrument=instrument, effective_on="2025-11-13",
                               source_url="https://www.example-lawblog.test/india/rules-2025.pdf")
                self.assertIn("cannot be current", "\n".join(legal.check_entry(e, "2026-10-27")))

    def test_ambiguous_numbered_citations_on_unofficial_sources_require_uncertainty(self):
        for instrument, provision in (
            ("MeitY notification dated 13 November 2025", "Rule 3"),
            ("The Rules, 2025", "Rule 3"),
            ("The Act", "Section 8(7)"),
            ("The Act", "Sections 43–44"),
        ):
            with self.subTest(instrument=instrument, provision=provision):
                e = self.entry(provision, instrument=instrument, effective_on="2025-11-13",
                               source_url="https://www.example-lawblog.test/india/rules-2025.pdf")
                self.assertIn("Identify the instrument", legal.check_entry(e, "2026-10-27")[0])
                e["status"] = "uncertain"
                self.assertIn("without a commencement date", legal.check_entry(e, "2026-10-27")[0])
                e["effective_on"] = None
                self.assertEqual(legal.check_entry(e, "2026-10-27"), [])
                self.assertTrue(legal.entry_warnings(e))

    def test_stale_future_duty_cannot_use_preparation_or_latest_date_to_bypass_guard(self):
        for instrument, expected in (
            ("Data Protection Rules, 2025", "cannot be future"),
            ("The Rules, 2025", "Identify the instrument"),
        ):
            for field in ("preparation_on", "effective_by"):
                with self.subTest(instrument=instrument, field=field):
                    e = self.entry("Rule 3", "future", instrument=instrument,
                                   source_url="https://www.example-lawblog.test/india/rules-2025.pdf",
                                   **{field: "2028-01-01"})
                    self.assertIn(expected, "\n".join(legal.check_entry(e, "2027-06-01")))

    def test_dpdp_source_and_alias_override_other_instrument_markers(self):
        operative = (
            "https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf"
        )
        for instrument, source_url, provision in (
            ("IT Act 2000", operative, "Section 5"),
            ("SPDI Rules 2011; DPDPR2025", "https://www.meity.gov.in/opaque.pdf", "Rule 3"),
        ):
            e = self.entry(provision, instrument=instrument, source_url=source_url)
            self.assertIn("cannot be current", legal.check_entry(e, "2026-10-27")[0])

    def test_unknown_nonofficial_source_retains_generic_checks_with_warning(self):
        for provision in ("Clause 5", "Rule 24", "Section 45"):
            with self.subTest(provision=provision):
                e = self.entry(provision, instrument="Other law", source_url="https://law.example.test/act")
                self.assertEqual(legal.check_entry(e, "2026-10-27"), [])
                self.assertIn("authority is unverified", legal.entry_warnings(e)[0])

    def test_other_instruments_keep_existing_validation(self):
        for instrument, provision, source_url in (
            ("SPDI Rules 2011, G.S.R. 313(E)", "Rule 4",
             "https://emb.mes.gov.in/Common/help/gsr3_10511.pdf"),
            ("SPDI Rules 2011", "Rule 4",
             "https://www.meity.gov.in/writereaddata/files/GSR313E_10511%281%29_0.pdf"),
            ("Information Technology Act, 2000", "Section 43A",
             "https://www.meity.gov.in/static/uploads/other-act.pdf"),
            ("CERT-In Directions 2022", "Direction (ii)", "https://www.cert-in.org.in/"),
        ):
            with self.subTest(instrument=instrument):
                e = self.entry(provision, instrument=instrument, source_url=source_url,
                               effective_on="2011-04-11")
                self.assertEqual(legal.entry_warnings(e), [])
                self.assertEqual(legal.check_entry(e, "2026-10-27"), [])


if __name__ == "__main__":
    unittest.main()
