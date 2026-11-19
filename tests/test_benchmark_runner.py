import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "benchmark" / "runner.py"
SPEC = importlib.util.spec_from_file_location("benchmark_runner", RUNNER)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class BenchmarkRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.benchmark = self.root / "checkout" / "benchmark"
        self.manifest = {"schema_version": 1, "development": [], "held_out": []}
        for stack in runner.STACKS:
            for index in range(6):
                case_id = f"{stack}-{index}"
                relative = f"cases/{case_id}/case.json"
                self.manifest["development"].append(
                    {"id": case_id, "stack": stack, "path": relative}
                )
                self.add_case(self.benchmark / relative, case_id, stack)
            self.manifest["held_out"].extend(
                {"id": f"{stack}-private-{index}", "stack": stack, "status": "pending"}
                for index in range(2)
            )
        write_json(self.benchmark / "manifest.json", self.manifest)
        self.cases, _, _ = runner.load_cases(self.benchmark, None)
        self.case = self.cases["shopify-0"]

    def add_case(self, path, case_id, stack):
        write_json(path, {
            "id": case_id, "stack": stack, "mode": "public", "audit_date": "2026-11-18",
            "input": {"artifacts": [{"path": "notice.txt"}, {"path": "other.txt"}]},
            "expected": {
                "findings": [{"id": "notice-gap", "severity": "critical",
                              "evidence_refs": ["notice.txt"]}],
                "sampled_checks": ["Notice link checked"],
                "unknowns": ["Deletion process unavailable"],
                "seeded_criticals": ["notice-gap"],
                "forbidden_claims": ["Verified deletion"],
                "plan_acceptance_checks": ["Include retest of the notice link"],
            },
        })
        (path.parent / "notice.txt").write_text("Synthetic missing notice")
        (path.parent / "other.txt").write_text("Unrelated evidence")

    def result(self, run_id="run-one", captured=False, case=None):
        case = case or self.case
        path = self.root / run_id / case["id"] / "result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        report = path.parent / "report.txt"
        report.write_text("Synthetic audit description")
        collection = {"status": "pending", "origin": "none", "reason": "No executed capture",
                      "artifacts": []}
        if captured:
            capture = path.parent / "capture.txt"
            capture.write_text("Unit test only")
            collection = {
                "status": "captured", "origin": "adapter", "reason": None,
                "artifacts": [{"path": "capture.txt",
                               "sha256": runner.sha256(capture.read_bytes()).hexdigest()}],
            }
        expected = case["expected"]
        result = {
            "schema_version": 1, "case_id": case["id"], "case_sha256": case["case_sha256"],
            "scope": case["scope"], "run_id": run_id,
            "metadata": {"started_at": None, "elapsed_seconds": None, "cost": None,
                         "tools": [{"name": "unit-test", "version": "1"}], "model": None},
            "collection": collection,
            "raw_report": {"path": "report.txt",
                           "sha256": runner.sha256(report.read_bytes()).hexdigest()},
            "assessment": {
                "verdict": "findings", "findings": copy.deepcopy(expected["findings"]),
                "unknowns": list(expected["unknowns"]),
                "sampled_checks": list(expected["sampled_checks"]),
            },
            "remediation": {
                "status": "proposed", "items": [
                    {"finding_id": "notice-gap", "action": "Add notice",
                     "verification": "Retest the notice link"}
                ],
            },
        }
        return path, result

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(RUNNER), "--benchmark-dir", str(self.benchmark),
             *map(str, args)], capture_output=True, text=True, check=False
        )

    def test_fixture_checks_keep_held_out_and_results_pending(self):
        completed = self.cli("--require-ready")
        self.assertEqual(completed.returncode, 1, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(len(summary["fixture_checks"]["cases"]), 24)
        self.assertEqual(len(summary["held_out_pending"]), 8)
        self.assertEqual(summary["runs"], {})
        self.assertEqual(summary["benchmark_gate"], "blocked")
        self.assertFalse(summary["release_claim_authorized"])
        self.assertIn("24 development", completed.stderr)

    def test_false_clear_cannot_pass_with_unreported_unknowns_and_no_judge(self):
        path, result = self.result(captured=True)
        result["assessment"].update(verdict="all_clear", findings=[], unknowns=[])
        result["remediation"] = {"status": "not_applicable", "items": []}
        write_json(path, result)
        completed = self.cli("--results", path.parents[1], "--require-ready")
        self.assertEqual(completed.returncode, 1, completed.stderr)
        summary = json.loads(completed.stdout)
        case = summary["runs"]["run-one"]["cases"][self.case["id"]]
        self.assertIn("false_all_clear", case["blockers"])
        self.assertIn("scope_unknown_mismatch", case["blockers"])
        self.assertIn("independent_judgment_pending", case["blockers"])
        self.assertIn("notice-gap", case["assessment"]["critical_misses"])
        self.assertFalse(summary["release_claim_authorized"])
        self.assertIsNone(case["assessment"]["findings"]["precision"]["value"])

    def test_result_hash_changes_if_fixture_bytes_change(self):
        path, result = self.result()
        write_json(path, result)
        packet = self.benchmark / "cases" / self.case["id"] / "notice.txt"
        packet.write_text("Changed fixture")
        completed = self.cli("--results", path.parents[1])
        self.assertEqual(completed.returncode, 2)
        self.assertIn("case hash mismatch", completed.stderr)

    def test_rejects_empty_dummy_and_unsupported_records(self):
        path, original = self.result()
        cases = (
            ({}, "required property"),
            ({**original, "assessment": {**original["assessment"], "verdict": "passed"}},
             "'passed' is not one"),
            ({**original, "assessment": {"verdict": "inconclusive", "findings": [],
                                         "unknowns": [], "sampled_checks": []}},
             "assessment has no evidence-bearing claims"),
        )
        for result, message in cases:
            with self.subTest(result=result):
                write_json(path, result)
                with self.assertRaisesRegex(runner.InvalidBenchmark, message):
                    runner.load_result(path, "run-one", self.case)

    def test_rejects_duplicate_finding_ids_and_manifest_ids(self):
        path, result = self.result()
        finding = result["assessment"]["findings"][0]
        result["assessment"]["findings"].append({**finding, "severity": "high"})
        write_json(path, result)
        with self.assertRaisesRegex(runner.InvalidBenchmark, "Duplicate .* finding ID"):
            runner.load_result(path, "run-one", self.case)
        self.manifest["held_out"][0]["id"] = self.case["id"]
        write_json(self.benchmark / "manifest.json", self.manifest)
        with self.assertRaisesRegex(runner.InvalidBenchmark, "Duplicate manifest case ID"):
            runner.load_cases(self.benchmark, None)

    def test_label_copy_and_evidence_padding_do_not_score(self):
        for severity, refs in (("low", ["notice.txt"]), ("critical", ["other.txt"]),
                               ("critical", ["notice.txt", "other.txt"])):
            with self.subTest(severity=severity, refs=refs):
                path, result = self.result()
                result["assessment"]["findings"][0].update(severity=severity, evidence_refs=refs)
                result["assessment"]["sampled_checks"].append("Unseeded claim")
                write_json(path, result)
                loaded, digest = runner.load_result(path, "run-one", self.case)
                scored = runner.score_case(self.case, loaded, digest, None)
                findings = scored["assessment"]["findings"]
                self.assertEqual(findings["false_positives"], ["notice-gap"])
                self.assertEqual(findings["missed_known_gaps"], ["notice-gap"])
                self.assertEqual(findings["precision"]["value"], 0)
                self.assertEqual(findings["recall"]["value"], 0)
                self.assertIn("sampled_check_mismatch", scored["blockers"])

    def test_run_comparison_uses_only_same_case_pairs(self):
        first, left_result = self.result()
        second, right_result = self.result(run_id="run-two")
        unmatched, unmatched_result = self.result(run_id="run-two",
                                                  case=self.cases["shopify-1"])
        for path, result in ((first, left_result), (second, right_result),
                             (unmatched, unmatched_result)):
            write_json(path, result)
        completed = self.cli("--results", first.parents[1], "--results", second.parents[1])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        pair = summary["paired_comparisons"][0]
        self.assertEqual(pair["paired_case_sha256"], {self.case["id"]: self.case["case_sha256"]})
        self.assertEqual(pair["right_metrics"]["cases_scored"], 1)
        self.assertEqual(summary["runs"]["run-two"]["metrics"]["cases_scored"], 2)
        self.assertEqual(summary["benchmark_gate"], "blocked")

    def ledger(self, path, result):
        unit_test_verdict = {"status": "pass", "rationale": "Synthetic validator test only"}
        return {
            "schema_version": 1,
            "verification": {"verified_by": "unit-test", "verified_at": "2026-11-18T08:00:00Z",
                             "provenance_ref": "unit-test"},
            "records": [{
                "case_id": self.case["id"], "case_sha256": self.case["case_sha256"],
                "result_sha256": runner.sha256(path.read_bytes()).hexdigest(),
                "run_id": result["run_id"], "reviewer": "unit-test",
                "raw_report_sha256": result["raw_report"]["sha256"],
                "raw_report_verdict": "findings", "raw_report_verdict_confirmed": True,
                "model": "unit-test", "review_ref": "unit-test",
                "reviewed_at": "2026-11-18T08:00:00Z",
                **{key: unit_test_verdict for key in runner.JUDGMENTS},
            }],
        }

    def score_with_ledger(self, path, ledger, judge_path=None, pin=None):
        judge_path = judge_path or self.root / "private-ledger.json"
        write_json(judge_path, ledger)
        digest = pin or runner.sha256(judge_path.read_bytes()).hexdigest()
        return self.cli("--results", path.parents[1], "--judge-ledger", judge_path,
                        "--judge-ledger-sha256", digest)

    def test_judge_must_be_pinned_and_bound_to_exact_result(self):
        path, result = self.result(captured=True)
        write_json(path, result)
        ledger = self.ledger(path, result)
        ledger["records"][0]["result_sha256"] = "0" * 64
        completed = self.score_with_ledger(path, ledger, pin="1" * 64)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("differs from operator pin", completed.stderr)
        completed = self.score_with_ledger(path, ledger)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("bound to different input or result bytes", completed.stderr)

    def test_confirmed_matching_ledger_scores_case_and_disclaims_identity(self):
        path, result = self.result(captured=True)
        write_json(path, result)
        completed = self.score_with_ledger(path, self.ledger(path, result))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertFalse(summary["judge_ledger_verification_record"]["identity_verified_by_runner"])
        self.assertIn("identity not verified by runner", completed.stderr)
        case = summary["runs"]["run-one"]["cases"][self.case["id"]]
        self.assertEqual(case["status"], "ready_for_owner_review")
        self.assertTrue(case["assessment"]["raw_report_verdict_confirmed"])
        self.assertEqual(case["assessment"]["raw_report_verdict"], "findings")

    def test_raw_report_all_clear_survives_disagreeing_normalized_label(self):
        path, result = self.result(captured=True)
        report = path.parent / result["raw_report"]["path"]
        report.write_text("Everything passed. No gaps or limitations.")
        result["raw_report"]["sha256"] = runner.sha256(report.read_bytes()).hexdigest()
        write_json(path, result)
        ledger = self.ledger(path, result)
        ledger["records"][0]["raw_report_verdict"] = "all_clear"
        completed = self.score_with_ledger(path, ledger)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        run = json.loads(completed.stdout)["runs"]["run-one"]
        case = run["cases"][self.case["id"]]
        self.assertIn("raw_report_verdict_mismatch", case["blockers"])
        self.assertEqual(case["stage_readiness"]["judgment"], "blocked")
        self.assertEqual(run["metrics"]["false_all_clears"], 1)
        self.assertEqual(run["metrics"]["independent_mapping_passes"], 0)

    def test_ledger_requires_raw_verdict_review(self):
        path, result = self.result(captured=True)
        write_json(path, result)
        ledger = self.ledger(path, result)
        ledger["records"][0]["raw_report_verdict_confirmed"] = False
        completed = self.score_with_ledger(path, ledger)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        case = json.loads(completed.stdout)["runs"]["run-one"]["cases"][self.case["id"]]
        self.assertIn("raw_report_verdict_unconfirmed", case["blockers"])
        del ledger["records"][0]["raw_report_verdict_confirmed"]
        completed = self.score_with_ledger(path, ledger)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("raw_report_verdict_confirmed", completed.stderr)

    def test_zip_layout_rejects_ledger_in_repository_root(self):
        path, result = self.result(captured=True)
        write_json(path, result)
        checkout = self.benchmark.parent
        self.assertFalse((checkout / ".git").exists())
        completed = self.score_with_ledger(path, self.ledger(path, result),
                                           judge_path=checkout / "inside-ledger.json")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("must be outside the builder checkout", completed.stderr)

    def test_judgment_is_measurable_while_collection_is_pending(self):
        path, result = self.result()
        write_json(path, result)
        loaded, digest = runner.load_result(path, "run-one", self.case)
        unit_test_verdict = {"status": "pass", "rationale": "Synthetic validator test only"}
        judge = {"case_sha256": self.case["case_sha256"], "result_sha256": digest,
                 "raw_report_sha256": result["raw_report"]["sha256"],
                 "raw_report_verdict": "findings", "raw_report_verdict_confirmed": True,
                 **{key: unit_test_verdict for key in runner.JUDGMENTS}}
        with self.assertRaisesRegex(runner.InvalidBenchmark, "cannot pass without capture"):
            runner.score_case(self.case, loaded, digest, judge)
        judge["collection"] = {"status": "blocked", "rationale": "No capture was run"}
        scored = runner.score_case(self.case, loaded, digest, judge)
        self.assertEqual(scored["status"], "blocked")
        self.assertIn("collection_pending", scored["blockers"])
        self.assertEqual(scored["stage_readiness"], {
            "collection": "blocked", "judgment": "complete_for_case",
            "remediation": "complete_for_case",
        })

    def test_mutated_raw_report_rejects_result(self):
        path, result = self.result()
        write_json(path, result)
        (path.parent / result["raw_report"]["path"]).write_text("Human-edited text")
        with self.assertRaisesRegex(runner.InvalidBenchmark, "mismatched raw report"):
            runner.load_result(path, "run-one", self.case)

    def test_fixture_bytes_cannot_be_relabelled_as_capture(self):
        path, result = self.result(captured=True)
        capture = result["collection"]["artifacts"][0]
        source = self.benchmark / "cases" / self.case["id"] / "notice.txt"
        (path.parent / capture["path"]).write_bytes(source.read_bytes())
        capture["sha256"] = self.case["artifact_sha256"][source.name]
        write_json(path, result)
        loaded, digest = runner.load_result(path, "run-one", self.case)
        with self.assertRaisesRegex(runner.InvalidBenchmark, "fixture bytes cannot substitute"):
            runner.score_case(self.case, loaded, digest, None)

    def test_blind_copy_omits_answers_and_titles(self):
        reserved = self.manifest["held_out"][0]
        case_id = reserved["id"]
        private = self.root / "private-held-out"
        hidden_case = private / case_id / "case.json"
        self.add_case(hidden_case, case_id, reserved["stack"])
        definition = json.loads(hidden_case.read_text())
        definition["title"] = "Answer in title"
        write_json(hidden_case, definition)
        blind = self.root / "blind"
        alias_map = self.root / "private-aliases.json"
        completed = self.cli("--held-out", private, "--export-inputs", blind,
                             "--export-alias-map", alias_map, "--case-id", case_id)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        aliases = json.loads(alias_map.read_text())["aliases"]
        alias, = aliases
        self.assertEqual(aliases[alias], case_id)
        self.assertNotIn(case_id, alias)
        self.assertEqual(alias_map.stat().st_mode & 0o077, 0)
        exported = blind / alias
        brief = json.loads((exported / "brief.json").read_text())
        self.assertEqual(set(brief), {"id", "stack", "mode", "audit_date", "scope", "artifacts"})
        self.assertEqual(brief["id"], alias)
        self.assertNotIn(case_id, (exported / "brief.json").read_text())
        self.assertEqual({path.name for path in exported.iterdir()}, {"brief.json", "artifacts"})
        self.assertEqual((exported / "artifacts/notice.txt").read_bytes(),
                         (hidden_case.parent / "notice.txt").read_bytes())
        self.assertFalse((self.benchmark / case_id).exists())
        invalid_destination = self.benchmark / "private"
        invalid = self.cli("--held-out", private, "--export-inputs", invalid_destination,
                           "--export-alias-map", self.root / "another-map.json", "--case-id", case_id)
        self.assertEqual(invalid.returncode, 2)
        self.assertFalse(invalid_destination.exists())

    def test_development_blind_copy_hides_canonical_id_and_rejects_map_in_packet(self):
        blind = self.root / "dev-blind"
        case_id = self.case["id"]
        rejected = self.cli("--export-inputs", blind, "--export-alias-map", blind / "private.json",
                            "--case-id", case_id)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("outside the candidate packet", rejected.stderr)
        self.assertFalse(blind.exists())
        alias_map = self.root / "dev-private-map.json"
        completed = self.cli("--export-inputs", blind, "--export-alias-map", alias_map,
                             "--case-id", case_id)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        exported, = blind.iterdir()
        brief = json.loads((exported / "brief.json").read_text())
        self.assertEqual(exported.name, brief["id"])
        self.assertNotIn(case_id, exported.name)
        self.assertNotIn(case_id, json.dumps(brief))
        self.assertEqual(json.loads(alias_map.read_text())["aliases"], {brief["id"]: case_id})

    def test_empty_denominators_are_unmeasured(self):
        scored = runner.score_findings([], [], set())
        for metric in ("precision", "recall"):
            self.assertEqual(scored[metric], {"numerator": 0, "denominator": 0, "value": None})


if __name__ == "__main__":
    unittest.main()
