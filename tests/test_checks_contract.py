"""Enforce the fixture contract for every check shipped by the registry."""

from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checks.contract import Basis, Check, CheckResult, Fix, Need, Retest
from checks.evidence import EvidenceBundle
from checks.registry import registered_checks
from tests.test_fixture_hygiene import HYGIENE


CASES = {"positive": "gap", "negative": "ok", "insufficient": "could_not_check"}


def demo_check():
    need = Need("artifact", "labels.json", "/descriptive")

    def evaluate(evidence):
        ref = evidence.artifact_ref("labels.json", "descriptive")
        if evidence.resolve(ref) is True:
            return CheckResult("ok", "The supplied label is descriptive.", (ref,))
        return CheckResult(
            "gap", "The supplied label is missing a description.", (ref,),
            fix=Fix("Sample form", "Form maintainer", "Add a descriptive label.",
                    "The sample input has the visible label Delivery note.",
                    Retest((need,), "The new sample records a descriptive label.")),
        )

    return Check("GEN-DEMO", "generic", "Sample input label",
                 Basis("good_practice", note="A visible label identifies the input."), (need,), evaluate)


class FixtureContractTests(unittest.TestCase):
    def assert_fixtures(self, check, root):
        for name, expected in CASES.items():
            with self.subTest(check=check.id, case=name):
                folder = root / check.stack / check.id / name
                self.assertFalse(folder.is_symlink(), "Fixture symlinks are not allowed")
                for path in sorted(folder.rglob("*")):
                    self.assertFalse(path.is_symlink(), "Fixture symlinks are not allowed")
                    if path.is_file():
                        content = path.read_text(encoding="utf-8")
                        if path.suffix == ".json":
                            # Inspect decoded strings too, so JSON escaping cannot hide a URL.
                            content += "\n" + json.dumps(json.loads(content), ensure_ascii=False)
                        for match in HYGIENE.URL.finditer(content):
                            candidate = match.group().rstrip(".,;:!?)}")
                            if candidate.endswith("]") and "[" not in candidate:
                                candidate = candidate[:-1]
                            parts = urlsplit(candidate)
                            self.assertIsNone(parts.username, "Fixture URL includes credentials")
                            self.assertTrue(HYGIENE.reserved_hostname(parts.hostname),
                                            "Fixture URL uses a non-fixture hostname")
                case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
                self.assertEqual(case["expect"], expected)
                bundle = EvidenceBundle.from_directory(folder)
                result = check.run(bundle)
                self.assertEqual(result.status, expected)
                self.assertEqual(list(result.evidence_refs), case["refs"])
                for ref in result.evidence_refs:
                    self.assertTrue(bundle.resolves(ref), f"Unresolved evidence reference {ref!r}")
                if expected == "gap":
                    self.assertTrue(result.fix.target and result.fix.responsible_role and result.fix.summary)
                    self.assertTrue(result.fix.acceptance_test.strip())
                    self.assertTrue(result.fix.retest.recollect and result.fix.retest.closes_when.strip())
                if expected == "could_not_check":
                    self.assertTrue(result.missing and result.evidence_request)
                    self.assertIsNone(result.fix)

    def test_registered_checks_have_all_three_cases(self):
        for check in registered_checks():
            self.assert_fixtures(check, ROOT / "checks" / "fixtures")

    def test_fixture_enforcement_with_test_only_demo(self):
        check = demo_check()
        self.assertNotIn(check.id, {registered.id for registered in registered_checks()})
        self.assert_fixtures(check, ROOT / "tests" / "check_fixtures")

    def test_cli_detects_theme_and_plugin_source(self):
        for stack, artifact, source, check_id, status in (
            ("shopify", "shopify-theme.js", "analytics.track('shelf_zoom');\n", "SHP-01b", "gap"),
            ("woocommerce", "woocommerce-plugin.php",
             "<?php\nadd_filter('wp_privacy_personal_data_erasers', 'sample_erase');\n", "WOO-03b", "ok"),
        ):
            with self.subTest(stack=stack), TemporaryDirectory() as directory:
                (Path(directory) / artifact).write_text(source, encoding="utf-8")
                results = self.run_cli(directory)
                self.assertEqual({stack}, {row["stack"] for row in results})
                self.assertEqual(status, next(row["status"] for row in results if row["id"] == check_id))
                self.assertEqual([], self.run_cli(directory, "--stack", "generic"))

    def test_cli_runs_each_explicit_stack(self):
        with TemporaryDirectory() as directory:
            results = self.run_cli(directory, "--stack", "shopify", "--stack", "woocommerce")
        self.assertEqual({"shopify", "woocommerce"}, {row["stack"] for row in results})

    def run_cli(self, directory, *options):
        process = subprocess.run(
            [sys.executable, "-m", "checks", "run", directory, *options],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(0, process.returncode, process.stderr)
        return json.loads(process.stdout)

    def test_result_invariants(self):
        ref = "packet:/observations/0/forms"
        for args, kwargs in (
            (("gap", "Missing fix.", (ref,)), {}),
            (("ok", "Missing evidence."), {}),
            (("could_not_check", "Missing request."), {"missing": ("forms",)}),
            (("could_not_check", "Missing description."), {"evidence_request": "Supply forms."}),
            (("pass", "Unsupported status.", (ref,)), {}),
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    CheckResult(*args, **kwargs)

    def test_rule_citations_are_pinned(self):
        self.assertEqual(Basis("legal", citation="Rule 3").citation, "Rule 3")
        for citation in ("Rule 99", "Rule 3 and Rule 99", "Section 6"):
            with self.subTest(citation=citation):
                with self.assertRaises(ValueError):
                    Basis("legal", citation=citation)


if __name__ == "__main__":
    unittest.main()
