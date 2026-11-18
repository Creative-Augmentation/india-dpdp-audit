#!/usr/bin/env python3
"""Validate and score synthetic audit benchmark records offline."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
import re
from pathlib import Path, PurePosixPath
import stat
from tempfile import TemporaryDirectory
import sys
from time import perf_counter

from jsonschema import Draft202012Validator, FormatChecker

BENCHMARK = Path(__file__).resolve().parent
VERSION = "1.0.0"
STACKS = ("shopify", "woocommerce", "firebase", "generic")
JUDGMENTS = ("assessment_mapping", "expectations", "legal", "scope_restraint",
             "remediation", "collection")
STAGES = {
    "collection": ("collection_", "independent_judgment_", "independent_collection_"),
    "judgment": ("finding_", "critical_", "scope_", "sampled_", "false_",
                 "independent_judgment_", "independent_assessment_mapping_",
                 "independent_expectations_", "independent_legal_", "independent_scope_restraint_"),
    "remediation": ("remediation_", "independent_judgment_", "independent_remediation_"),
}
FORMAT = FormatChecker()
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
LINE_RANGE = re.compile(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?")


class InvalidBenchmark(ValueError):
    """Input does not meet the benchmark contract."""


def require(condition, message):
    if not condition:
        raise InvalidBenchmark(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def invalid_constant(value):
    raise InvalidBenchmark(f"Invalid JSON number {value!r}")


def read_file(path):
    require(stat.S_ISREG(path.stat().st_mode), f"Expected a regular file: {path}")
    return path.read_bytes()


def read_json(path):
    try:
        raw = read_file(path)
        return json.loads(raw, object_pairs_hook=unique_object,
                          parse_constant=invalid_constant), sha256(raw).hexdigest()
    except (UnicodeError, ValueError) as exc:
        raise InvalidBenchmark(f"{path}: {exc}") from exc


def validate(contract, value, source):
    validator = Draft202012Validator(
        {"$defs": CONTRACTS, "$ref": f"#/$defs/{contract}"},
        format_checker=FORMAT,
    )
    error = next(validator.iter_errors(value), None)
    if error:
        raise InvalidBenchmark(f"{source} {error.json_path}: {error.message}")


CONTRACTS = read_json(BENCHMARK / "schema/contracts.json")[0]["$defs"]


def local_file(root, relative):
    path = PurePosixPath(relative)
    require(not path.is_absolute() and path.as_posix() == relative
            and ".." not in path.parts and path.parts,
            f"Expected a normalized relative path: {relative!r}")
    resolved = (root / relative).resolve()
    require(resolved.is_relative_to(root.resolve()), f"Path escapes {root}: {relative}")
    return resolved


def outside_checkout(path, root, description):
    resolved = path.resolve()
    for anchor in (BENCHMARK, root.resolve()):
        checkout = next((parent for parent in (anchor, *anchor.parents)
                         if (parent / ".git").exists()), anchor)
        require(not resolved.is_relative_to(checkout),
                f"{description} must be outside the builder checkout: {path}")


def index_unique(rows, key, description):
    indexed = {}
    for row in rows:
        identity = key(row)
        require(identity not in indexed, f"Duplicate {description}: {identity}")
        indexed[identity] = row
    return indexed


def check_locations(locations, artifacts, allowed, source):
    require(isinstance(locations, dict), f"{source}: evidence locations must be an object")
    for name, anchors in locations.items():
        require(name in allowed and isinstance(anchors, list) and anchors,
                f"{source}: invalid evidence location list for {name}")
        for anchor in anchors:
            require(isinstance(anchor, str), f"{source}: evidence location must be a string")
            line = LINE_RANGE.fullmatch(anchor)
            if line:
                start, end = int(line[1]), int(line[2] or line[1])
                require(start <= end <= len(artifacts[name].splitlines()),
                        f"{source}: line range {anchor} is outside {name}")
                continue
            require(name.endswith(".json") and anchor.startswith("/"),
                    f"{source}: unsupported evidence location {name} {anchor}")
            node = json.loads(artifacts[name], object_pairs_hook=unique_object,
                              parse_constant=invalid_constant)
            for token in anchor.split("/")[1:]:
                require(not re.search(r"~(?:[^01]|$)", token),
                        f"{source}: malformed JSON pointer {anchor}")
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(node, dict) and token in node:
                    node = node[token]
                elif isinstance(node, list) and re.fullmatch(r"0|[1-9][0-9]*", token) \
                        and int(token) < len(node):
                    node = node[int(token)]
                else:
                    raise InvalidBenchmark(f"{source}: unresolved pointer {name} {anchor}")


def load_case(path, entry, cohort):
    case, definition_hash = read_json(path)
    validate("case", case, path)
    case_id = case["id"]
    require((case_id, case["stack"]) == (entry["id"], entry["stack"]),
            f"Case identity does not match manifest: {path}")
    artifact_bytes = {}
    artifact_hashes = {}
    for artifact in case["input"]["artifacts"]:
        name = artifact["path"]
        require(name not in artifact_hashes, f"{case_id}: duplicate artifact path {name}")
        artifact_path = local_file(path.parent, name)
        require(artifact_path != path, f"{case_id}: artifact points to the case definition")
        raw = read_file(artifact_path)
        require(bool(raw.strip()), f"{case_id}: empty fixture artifact {name}")
        artifact_bytes[name] = raw
        artifact_hashes[name] = sha256(raw).hexdigest()

    expected = case["expected"]
    expected_findings = index_unique(expected["findings"], lambda row: row["id"],
                                     f"{case_id} expected finding ID")
    require(all(set(row["evidence_refs"]) <= artifact_hashes.keys()
                for row in expected_findings.values()), f"{case_id}: unknown expected evidence path")
    require(set(expected["seeded_criticals"]) == {
        key for key, row in expected_findings.items() if row["severity"] == "critical"
    }, f"{case_id}: seeded critical IDs and critical findings differ")
    require(bool(expected_findings or expected["unknowns"] or expected["sampled_checks"]),
            f"{case_id}: no scored expectations")
    for finding in expected_findings.values():
        check_locations(finding.get("evidence_locations", {}), artifact_bytes,
                        set(finding["evidence_refs"]), case_id)
    assertion_labels = set().union(*(expected[key] for key in (
        "sampled_checks", "unknowns", "forbidden_claims", "plan_acceptance_checks"
    )))
    for label, locations in expected.get("supporting_evidence", {}).items():
        require(label in assertion_labels, f"{case_id}: supporting evidence for unknown assertion")
        check_locations(locations, artifact_bytes, artifact_hashes, case_id)
    scope = case.get("scope", case["input"].get("scope", case["mode"]))
    require(isinstance(scope, str) and scope.strip(), f"{case_id}: scope must be nonempty text")
    fingerprint = json.dumps({"definition_sha256": definition_hash, "artifacts": artifact_hashes},
                             sort_keys=True, separators=(",", ":")).encode()
    return {
        "source_dir": path.parent,
        "id": case_id,
        "stack": case["stack"],
        "cohort": cohort,
        "scope": scope,
        "mode": case["mode"],
        "audit_date": case["audit_date"],
        "case_sha256": sha256(fingerprint).hexdigest(),
        "definition_sha256": definition_hash,
        "artifact_sha256": artifact_hashes,
        "expected": expected,
    }


def load_cases(root, held_out):
    manifest_path = root / "manifest.json"
    manifest, manifest_hash = read_json(manifest_path)
    validate("manifest", manifest, manifest_path)
    development, reserved = manifest["development"], manifest["held_out"]
    index_unique(development + reserved, lambda row: row["id"], "manifest case ID")
    index_unique(development, lambda row: row["path"], "development case path")
    for entries, per_stack in ((development, 6), (reserved, 2)):
        require(Counter(row["stack"] for row in entries) ==
                Counter({stack: per_stack for stack in STACKS}),
                f"Manifest must reserve {per_stack} cases per stack in this cohort")
    cases = {
        entry["id"]: load_case(local_file(root, entry["path"]), entry, "development")
        for entry in development
    }
    if held_out is not None:
        outside_checkout(held_out, root, "Held-out cases")
        require(held_out.is_dir(), f"Expected a held-out directory: {held_out}")
        supplied = {entry.name for entry in held_out.iterdir() if entry.is_dir()}
        require(supplied <= {entry["id"] for entry in reserved}, "Unreserved held-out case directory")
        for entry in reserved:
            if entry["id"] in supplied:
                path = local_file(held_out, f'{entry["id"]}/case.json')
                cases[entry["id"]] = load_case(path, entry, "held_out")
    pending = [row for row in reserved if row["id"] not in cases]
    return cases, pending, manifest_hash


def export_inputs(root, held_out, output, case_ids):
    """Write a blind packet with neutral metadata and only declared input artifacts."""
    output = output.resolve()
    outside_checkout(output, root, "Blind export")
    require(not output.exists(), f"Blind export destination already exists: {output}")
    require(output.parent.is_dir(), f"Blind export parent directory does not exist: {output.parent}")
    cases, _, _ = load_cases(root, held_out)
    require(case_ids and len(set(case_ids)) == len(case_ids), "Supply unique case IDs for export")
    require(set(case_ids) <= cases.keys(), "Blind export contains unknown or unavailable case IDs")
    with TemporaryDirectory(dir=output.parent) as tmp:
        packet = Path(tmp) / "packet"
        packet.mkdir(mode=0o700)
        for case_id in case_ids:
            case = cases[case_id]
            destination = packet / case_id
            destination.mkdir()
            metadata = {key: case[key] for key in ("id", "stack", "mode", "audit_date", "scope")}
            metadata["artifacts"] = dict(case["artifact_sha256"])
            (destination / "brief.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            for name, digest in case["artifact_sha256"].items():
                raw = read_file(local_file(case["source_dir"], name))
                require(sha256(raw).hexdigest() == digest, f"{case_id}: fixture changed during export")
                target = destination / "artifacts" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        require(not output.exists(), f"Blind export destination already exists: {output}")
        packet.rename(output)


def load_judges(path, pinned_hash, root):
    require((path is None) == (pinned_hash is None),
            "Provide both --judge-ledger and --judge-ledger-sha256")
    if path is None:
        return {}, None
    outside_checkout(path, root, "Independent judge ledger")
    ledger, actual_hash = read_json(path)
    require(actual_hash == pinned_hash, "Judge ledger hash differs from operator pin")
    validate("judge_ledger", ledger, path)
    records = index_unique(ledger["records"], lambda row: (row["run_id"], row["case_id"]),
                           "judge ledger run and case ID")
    return records, {"sha256": actual_hash, **ledger["verification"]}


def check_collection(path, collection, metadata):
    status = collection["status"]
    if status != "captured":
        require(collection["origin"] == "none" and not collection["artifacts"]
                and collection["reason"], f"{path}: pending or blocked collection needs a reason")
        return
    require(collection["origin"] != "none" and collection["artifacts"]
            and collection["reason"] is None, f"{path}: captured collection requires evidence")
    require(metadata["tools"], f"{path}: captured collection requires tool metadata")
    artifacts = index_unique(collection["artifacts"], lambda row: row["path"],
                             f"{path} collection artifact path")
    for name, artifact in artifacts.items():
        artifact_path = local_file(path.parent, name)
        require(artifact_path != path and artifact_path != path.parent / "result.json",
                f"{path}: capture artifact points to a result record")
        raw = read_file(artifact_path)
        require(bool(raw.strip()) and sha256(raw).hexdigest() == artifact["sha256"],
                f"{path}: empty or mismatched capture artifact {name}")


def load_result(path, run_id, case):
    result, result_hash = read_json(path)
    validate("result", result, path)
    require(result["run_id"] == run_id and result["case_id"] == case["id"],
            f"{path}: result run or case ID mismatch")
    require(result["case_sha256"] == case["case_sha256"], f"{path}: case hash mismatch")
    require(result["scope"] == case["scope"], f"{path}: scope differs from pinned case")
    report = result["raw_report"]
    raw_path = local_file(path.parent, report["path"])
    require(raw_path != path, f"{path}: raw report points to result record")
    raw = read_file(raw_path)
    require(bool(raw.strip()) and sha256(raw).hexdigest() == report["sha256"],
            f"{path}: empty or mismatched raw report")
    require(all(report["sha256"] != item["sha256"] for item in result["collection"]["artifacts"]),
            f"{path}: raw report cannot substitute for capture evidence")
    check_collection(path, result["collection"], result["metadata"])

    assessment = result["assessment"]
    findings = index_unique(assessment["findings"], lambda row: row["id"], f"{path} finding ID")
    available_evidence = case["artifact_sha256"].keys() | {
        artifact["path"] for artifact in result["collection"]["artifacts"]
    }
    require(all(set(row["evidence_refs"]) <= available_evidence for row in findings.values()),
            f"{path}: finding references unavailable evidence")
    require(findings or assessment["unknowns"] or assessment["sampled_checks"],
            f"{path}: assessment has no evidence-bearing claims")
    if assessment["verdict"] == "findings":
        require(findings, f"{path}: findings verdict requires at least one finding")
    if assessment["verdict"] == "all_clear":
        require(not findings and not assessment["unknowns"],
                f"{path}: all-clear conflicts with reported findings or unknowns")

    remediation = result["remediation"]
    items = index_unique(remediation["items"], lambda row: row["finding_id"],
                         f"{path} remediation finding ID")
    require(items.keys() <= findings.keys(), f"{path}: remediation references unreported findings")
    require(bool(items) == (remediation["status"] == "proposed"),
            f"{path}: proposed remediation requires items; other statuses require empty items")
    require(remediation["status"] != "not_applicable" or not findings,
            f"{path}: remediation cannot be not applicable with reported findings")
    return result, result_hash


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def score_labels(expected, reported):
    expected, reported = set(expected), set(reported)
    matches = expected & reported
    return {
        "matched": sorted(matches),
        "missing": sorted(expected - reported),
        "unexpected": sorted(reported - expected),
        "precision": rate(len(matches), len(reported)),
        "recall": rate(len(matches), len(expected)),
    }


def score_findings(expected, reported, captured):
    expected_by_id = {row["id"]: row for row in expected}
    reported_by_id = {row["id"]: row for row in reported}
    mismatches = {}
    for key in expected_by_id.keys() & reported_by_id.keys():
        target, actual = expected_by_id[key], reported_by_id[key]
        disputed = set(actual["evidence_refs"]) - captured
        reasons = []
        if target["severity"] != actual["severity"]:
            reasons.append("severity")
        if set(target["evidence_refs"]) != disputed:
            reasons.append("fixture_evidence")
        if reasons:
            mismatches[key] = reasons
    matched = (expected_by_id.keys() & reported_by_id.keys()) - mismatches.keys()
    false_positives = reported_by_id.keys() - matched
    missed = expected_by_id.keys() - matched
    return {
        "matched": sorted(matched), "false_positives": sorted(false_positives),
        "missed_known_gaps": sorted(missed), "mismatches": mismatches,
        "precision": rate(len(matched), len(reported)),
        "recall": rate(len(matched), len(expected)),
    }


def score_case(case, result, result_hash, judge):
    expected = case["expected"]
    assessment = result["assessment"]
    collection, remediation = result["collection"], result["remediation"]
    captures = {item["path"] for item in collection["artifacts"]}
    require(not captures & case["artifact_sha256"].keys(),
            f'{case["id"]}: capture paths overlap fixture paths')
    require(not set(case["artifact_sha256"].values()) & {
        item["sha256"] for item in collection["artifacts"]
    }, f'{case["id"]}: fixture bytes cannot substitute for recorded capture evidence')
    findings = score_findings(expected["findings"], assessment["findings"], captures)
    unknowns = score_labels(expected["unknowns"], assessment["unknowns"])
    samples = score_labels(expected["sampled_checks"], assessment["sampled_checks"])
    critical_misses = sorted(set(expected["seeded_criticals"]) & set(findings["missed_known_gaps"]))
    false_all_clear = assessment["verdict"] == "all_clear" and bool(
        expected["findings"] or expected["unknowns"] or samples["missing"]
        or collection["status"] != "captured"
    )
    blockers = []
    if collection["status"] != "captured":
        blockers.append(f'collection_{collection["status"]}')
    if findings["false_positives"] or findings["missed_known_gaps"]:
        blockers.append("finding_mismatch")
    if critical_misses:
        blockers.append("critical_miss")
    if unknowns["missing"] or unknowns["unexpected"]:
        blockers.append("scope_unknown_mismatch")
    if samples["missing"] or samples["unexpected"]:
        blockers.append("sampled_check_mismatch")
    if false_all_clear:
        blockers.append("false_all_clear")
    if remediation["status"] in {"pending", "blocked"}:
        blockers.append(f'remediation_{remediation["status"]}')
    plan_coverage = score_labels([row["id"] for row in assessment["findings"]],
                                 [row["finding_id"] for row in remediation["items"]])
    if plan_coverage["missing"]:
        blockers.append("remediation_coverage_incomplete")

    if judge is None:
        blockers.append("independent_judgment_pending")
    else:
        require(judge["case_sha256"] == case["case_sha256"]
                and judge["result_sha256"] == result_hash
                and judge["raw_report_sha256"] == result["raw_report"]["sha256"],
                f'{case["id"]}: independent judgment is bound to different input or result bytes')
        require(judge["collection"]["status"] != "pass" or collection["status"] == "captured",
                f'{case["id"]}: collection review cannot pass without capture evidence')
        for dimension in JUDGMENTS:
            if judge[dimension]["status"] != "pass":
                blockers.append(f'independent_{dimension}_{judge[dimension]["status"]}')
    return {
        "status": "blocked" if blockers else "ready_for_owner_review",
        "blockers": blockers,
        "case_sha256": case["case_sha256"],
        "result_sha256": result_hash,
        "raw_report": result["raw_report"],
        "scope": result["scope"],
        "metadata": result["metadata"],
        "collection": collection,
        "assessment": {
            "verdict": assessment["verdict"], "findings": findings,
            "scope_unknowns": unknowns, "sampled_checks": samples,
            "critical_misses": critical_misses, "false_all_clear": false_all_clear,
        },
        "remediation": {"status": remediation["status"], "finding_coverage": plan_coverage},
        "stage_readiness": {
            stage: "blocked" if any(reason.startswith(prefixes) for reason in blockers)
            else "complete_for_case"
            for stage, prefixes in STAGES.items()
        },
        "assessment_mapping_status": (
            judge["assessment_mapping"]["status"] if judge else "provisional"
        ),
        "independent_judgment": judge,
    }


def aggregate_labels(scores):
    counts = {key: sum(len(row[key]) for row in scores)
              for key in ("matched", "missing", "unexpected")}
    return {
        **counts,
        "precision": rate(counts["matched"], counts["matched"] + counts["unexpected"]),
        "recall": rate(counts["matched"], counts["matched"] + counts["missing"]),
    }


def aggregate(scores):
    measured = [row for row in scores.values() if "assessment" in row]
    finding_scores = [row["assessment"]["findings"] for row in measured]
    matched = sum(len(row["matched"]) for row in finding_scores)
    false_positives = sum(len(row["false_positives"]) for row in finding_scores)
    missed = sum(len(row["missed_known_gaps"]) for row in finding_scores)
    return {
        "cases_scored": len(measured),
        "cases_missing_results": len(scores) - len(measured),
        "stage_readiness": {
            stage: {
                "cases_complete": sum(
                    row.get("stage_readiness", {}).get(stage) == "complete_for_case"
                    for row in scores.values()
                ),
                "cases_required": len(scores),
            }
            for stage in STAGES
        },
        "cases_with_captured_collection": sum(
            row["collection"]["status"] == "captured" for row in measured),
        "independent_mapping_passes": sum(
            row["assessment_mapping_status"] == "pass" for row in measured),
        "independent_judgments_present": sum(
            row["independent_judgment"] is not None for row in measured),
        "findings": {
            "matched": matched,
            "false_positives": false_positives,
            "missed_known_gaps": missed,
            "critical_misses": sum(len(row["assessment"]["critical_misses"]) for row in measured),
            "precision": rate(matched, matched + false_positives),
            "recall": rate(matched, matched + missed),
        },
        "scope_unknowns": aggregate_labels([row["assessment"]["scope_unknowns"] for row in measured]),
        "sampled_checks": aggregate_labels([row["assessment"]["sampled_checks"] for row in measured]),
        "remediation_coverage": aggregate_labels(
            [row["remediation"]["finding_coverage"] for row in measured]
        ),
        "false_all_clears": sum(row["assessment"]["false_all_clear"] for row in measured),
        "blockers": dict(Counter(reason for row in scores.values() for reason in row["blockers"])),
    }


def load_run(directory, cases, judges):
    # The directory name is the run ID; results use <case_id>/result.json.
    require(directory.is_dir(), f"Expected a results directory: {directory}")
    run_id = directory.name
    require(IDENTIFIER.fullmatch(run_id),
            f"Invalid run ID: {run_id}")
    supplied = {}
    for child in directory.iterdir():
        if child.is_dir():
            require(child.name in cases, f"{run_id}: unrecognized case directory {child.name}")
            supplied[child.name] = local_file(directory, f"{child.name}/result.json")
    require(supplied, f"{run_id}: results directory is empty")
    scores = {}
    used_judgments = set()
    for case_id, case in cases.items():
        if case_id not in supplied:
            scores[case_id] = {"status": "blocked", "blockers": ["result_missing"],
                               "case_sha256": case["case_sha256"]}
            continue
        result, result_hash = load_result(supplied[case_id], run_id, case)
        judgment_key = (run_id, case_id)
        judge = judges.get(judgment_key)
        scores[case_id] = score_case(case, result, result_hash, judge)
        if judge is not None:
            used_judgments.add(judgment_key)
    by_stack = {
        stack: aggregate({case_id: scores[case_id] for case_id, case in cases.items()
                          if case["stack"] == stack})
        for stack in STACKS
    }
    by_cohort = {
        cohort: aggregate({case_id: scores[case_id] for case_id, case in cases.items()
                           if case["cohort"] == cohort})
        for cohort in ("development", "held_out")
    }
    return {"cases": scores, "metrics": aggregate(scores), "by_stack": by_stack,
            "by_cohort": by_cohort}, used_judgments


def compare_runs(runs):
    comparisons = []
    for (left_id, left), (right_id, right) in combinations(runs.items(), 2):
        paired = {}
        for case_id in left["cases"].keys() & right["cases"].keys():
            a, b = left["cases"][case_id], right["cases"][case_id]
            if "assessment" not in a or "assessment" not in b:
                continue
            require(a["case_sha256"] == b["case_sha256"], f"{case_id}: comparison hash mismatch")
            paired[case_id] = (a, b)
        pairs = {case_id: rows[0]["case_sha256"] for case_id, rows in sorted(paired.items())}
        left_matched = aggregate({key: rows[0] for key, rows in paired.items()})
        right_matched = aggregate({key: rows[1] for key, rows in paired.items()})
        comparisons.append({"left_run_id": left_id, "right_run_id": right_id,
                            "paired_case_sha256": pairs,
                            "left_metrics": left_matched, "right_metrics": right_matched})
    return comparisons


def run(args):
    started_at = datetime.now(timezone.utc).isoformat()
    start = perf_counter()
    root = args.benchmark_dir.resolve()
    cases, pending, manifest_hash = load_cases(root, args.held_out)
    judges, verification = load_judges(args.judge_ledger, args.judge_ledger_sha256, root)
    runs = {}
    used_judgments = set()
    for directory in args.results:
        require(directory.name not in runs, f"Duplicate run ID: {directory.name}")
        if args.held_out is not None:
            outside_checkout(directory, root, "Runs evaluated with held-out cases")
        runs[directory.name], used = load_run(directory, cases, judges)
        used_judgments.update(used)
    require(used_judgments == judges.keys(), "Judge ledger includes records for unsupplied results")
    blockers = []
    if pending:
        blockers.append("held_out_packets_pending")
    if not runs:
        blockers.append("results_pending")
    if len(runs) < 2:
        blockers.append("repeated_runs_pending")
    if any(run["metrics"]["blockers"] for run in runs.values()):
        blockers.append("run_blockers_present")
    fixtures = {case_id: {key: value for key, value in case.items() if key not in {"expected", "source_dir"}}
                for case_id, case in cases.items()}
    return {
        "schema_version": 1,
        "runner": {"version": VERSION, "python_version": sys.version.split()[0],
                   "started_at": started_at,
                   "elapsed_seconds": perf_counter() - start, "cost": None},
        "manifest_sha256": manifest_hash,
        "fixture_checks": {
            "status": "validated", "cases": fixtures,
            "development_cases_validated": sum(case["cohort"] == "development" for case in cases.values()),
            "held_out_cases_validated": sum(case["cohort"] == "held_out" for case in cases.values()),
        },
        "held_out_pending": pending,
        "native_collection_status": ("capture_records_supplied" if any(
            row["metrics"]["cases_with_captured_collection"] for row in runs.values()
        ) else "unmeasured"),
        "independent_judgment_status": "ledger_supplied" if verification else "pending",
        "judge_ledger_verification_record": verification,
        "runs": runs,
        "paired_comparisons": compare_runs(runs),
        "benchmark_gate": "blocked" if blockers else "ready_for_owner_review",
        "release_claim_authorized": False,
        "blockers": blockers,
    }


def human_summary(summary):
    fixtures = summary["fixture_checks"]["cases"]
    counts = Counter(case["cohort"] for case in fixtures.values())
    lines = [
        f'Fixture checks validated {counts["development"]} development and '
        f'{counts["held_out"]} held-out definitions and their artifact hashes.',
        f'Held-out packets pending: {len(summary["held_out_pending"])}.',
        f'Native collection: {summary["native_collection_status"].replace("_", " ")}.',
        f'Independent judgment: {summary["independent_judgment_status"].replace("_", " ")}.',
    ]
    for run_id, record in summary["runs"].items():
        metrics = record["metrics"]
        findings = metrics["findings"]
        lines.append(
            f'{run_id}: {metrics["cases_scored"]} scored, '
            f'{metrics["cases_missing_results"]} missing results, '
            f'{metrics["cases_with_captured_collection"]} capture records, '
            f'{metrics["independent_judgments_present"]} independent judgment records, '
            f'{findings["matched"]} matched findings, {findings["false_positives"]} false positives, '
            f'{findings["missed_known_gaps"]} missed gaps ({findings["critical_misses"]} critical), '
            f'{metrics["false_all_clears"]} false all-clears.'
        )
        for stage, coverage in metrics["stage_readiness"].items():
            lines.append(f'{run_id} {stage}: {coverage["cases_complete"]}/'
                         f'{coverage["cases_required"]} cases complete.')
        for metric in ("precision", "recall"):
            row = findings[metric]
            value = (f'{row["numerator"]}/{row["denominator"]}' if row["denominator"]
                     else "unmeasured")
            lines.append(f'{run_id} {metric}: {value}.')
    waiting = ", ".join(summary["blockers"])
    lines.append(f'Benchmark gate: {summary["benchmark_gate"]}.' +
                 (f" Blockers: {waiting}." if waiting else ""))
    lines.append("Release claim authorization requires owner review.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, default=BENCHMARK)
    parser.add_argument("--held-out", type=Path)
    parser.add_argument("--results", type=Path, action="append", default=[])
    parser.add_argument("--export-inputs", type=Path,
                        help="write a blind packet at a new location outside the checkout")
    parser.add_argument("--case-id", action="append", default=[], help="case to include in blind export")
    parser.add_argument("--judge-ledger", type=Path)
    parser.add_argument("--judge-ledger-sha256")
    parser.add_argument("--require-ready", action="store_true",
                        help="exit 1 when benchmark evidence is incomplete or has blockers")
    args = parser.parse_args(argv)
    try:
        if args.export_inputs:
            require(not (args.results or args.judge_ledger or args.judge_ledger_sha256
                         or args.require_ready), "Blind export cannot be combined with scoring")
            export_inputs(args.benchmark_dir.resolve(), args.held_out, args.export_inputs,
                          args.case_id)
            print(f"Wrote blind inputs for {len(args.case_id)} case(s).", file=sys.stderr)
            return 0
        require(not args.case_id, "--case-id requires --export-inputs")
        summary = run(args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Invalid benchmark input: {exc}\n")
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    print(human_summary(summary), file=sys.stderr)
    return int(args.require_ready and summary["benchmark_gate"] == "blocked")


if __name__ == "__main__":
    sys.exit(main())
