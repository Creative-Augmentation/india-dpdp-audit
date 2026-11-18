"""Validate, render, and compare local India DPDP audit records."""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "assets" / "audit.schema.json"
AUDIT_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
COLLECTIONS = ("coverage", "evidence", "data_map", "legal_ledger", "findings", "actions")
EVIDENCE_MODES = {
    "public_browser": "public",
    "public_source": "public",
    "repository_code": "repository",
    "internal_record": "internal",
    "staging_check": "staging",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def reject_constant(token):
    raise ValueError(f"invalid JSON constant {token}")


def read_json(path: Path):
    with path.open(encoding="utf-8") as content:
        return json.load(content, object_pairs_hook=unique_object, parse_constant=reject_constant)


def schema_validator():
    schema = read_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def validate(record, validator):
    errors = sorted(
        (f"{error.json_path}: {error.message}" for error in validator.iter_errors(record)),
    )
    return errors or check_consistency(record)


def evidence_host(locator):
    if any(char.isspace() or not char.isprintable() for char in locator):
        return None
    try:
        url = urlsplit(locator)
        if url.scheme in {"http", "https"} and url.hostname and url.username is None and url.port != 0:
            return url.hostname.removesuffix(".")
    except ValueError:
        pass
    return None


def capture_time(evidence):
    value = evidence["captured_at"].upper().replace("Z", "+00:00")
    # Python 3.10 expects exactly three or six fractional second digits.
    value = re.sub(r"\.([0-9]+)", lambda match: "." + match[1][:6].ljust(6, "0"), value)
    return datetime.fromisoformat(value)


def check_consistency(record: dict[str, Any]) -> list[str]:
    errors = []
    audit_date = date.fromisoformat(record["audit_date"])
    scope = record["scope"]
    modes = set(scope["modes"])
    domains = set(scope["authorized_domains"])
    repositories = {
        (item["locator"], item["revision"]) for item in scope.get("authorized_repositories", [])
    }
    if "public" in modes and not domains:
        errors.append("public scope requires at least one authorized domain")
    if ("repository" in modes) != bool(repositories):
        errors.append("repository scope and authorized repositories must be declared together")

    indexes = {name: {} for name in COLLECTIONS}
    used_ids = set()
    for name, index in indexes.items():
        for item in record[name]:
            identifier = item["id"]
            if identifier in used_ids:
                errors.append(f"{name}: duplicate ID {identifier}")
            used_ids.add(identifier)
            index[identifier] = item

    def references(owner, field, collection):
        index = indexes[collection]
        result = []
        for identifier in owner[field]:
            if identifier in index:
                result.append(index[identifier])
            else:
                errors.append(f"{owner['id']}.{field}: unknown {collection} ID {identifier}")
        return result

    def has_direct_evidence(items):
        return any(item["status"] == "direct" for item in items)

    for evidence in record["evidence"]:
        identifier = evidence["id"]
        kind = evidence["kind"]
        mode = EVIDENCE_MODES.get(kind)
        if (kind == "owner_statement") != (evidence["status"] == "asserted"):
            errors.append(f"{identifier}: asserted evidence must be an owner_statement and vice versa")
        if mode and mode not in modes:
            errors.append(f"{identifier}: {kind} requires {mode} scope")
        repository = (evidence.get("repository"), evidence.get("revision"))
        if kind == "repository_code":
            if repository not in repositories:
                errors.append(f"{identifier}: repository evidence requires an authorized repository and revision")
        elif any(repository):
            errors.append(f"{identifier}: repository and revision are only valid for repository_code")
        if mode == "public" and evidence_host(evidence["locator"]) not in domains:
            errors.append(f"{identifier}: public locator must be an HTTP(S) URL on an authorized domain")
        if capture_time(evidence).astimezone(AUDIT_TIMEZONE).date() > audit_date:
            errors.append(f"{identifier}: evidence captured after the audit date")

    for journey in record["coverage"]:
        evidence = references(journey, "evidence_ids", "evidence")
        if journey["status"] == "inspected" and not has_direct_evidence(evidence):
            errors.append(f"{journey['id']}: an inspected journey requires direct evidence")

    for flow in record["data_map"]:
        identifier = flow["id"]
        if flow["journey_id"] not in indexes["coverage"]:
            errors.append(f"{identifier}.journey_id: unknown coverage ID {flow['journey_id']}")
        evidence = references(flow, "evidence_ids", "evidence")
        if flow["observed_facts"] and not has_direct_evidence(evidence):
            errors.append(f"{identifier}: observed facts require direct evidence")
        for claim in flow["owner_claims"]:
            evidence = references({"id": identifier, **claim}, "evidence_ids", "evidence")
            if any(item["kind"] != "owner_statement" for item in evidence):
                errors.append(f"{identifier}: owner claims require owner_statement evidence")

    for entry in record["legal_ledger"]:
        identifier = entry["id"]
        effective = date.fromisoformat(entry["effective_on"]) if entry["effective_on"] else None
        effective_by = date.fromisoformat(entry["effective_by"]) if "effective_by" in entry else None
        verified = date.fromisoformat(entry["verified_on"])
        published = date.fromisoformat(entry["published_on"]) if entry["published_on"] else None
        if evidence_host(entry["source_url"]) is None:
            errors.append(f"{identifier}: source_url must be a valid HTTPS source URL")
        if verified > audit_date:
            errors.append(f"{identifier}: source verification is after the audit date")
        if published and published > verified:
            errors.append(f"{identifier}: publication is after source verification")
        if effective and effective_by:
            errors.append(f"{identifier}: effective_by is only valid when the exact effective date is unresolved")
        latest_commencement = effective or effective_by
        if entry["status"] == "current" and (latest_commencement is None or latest_commencement > audit_date):
            errors.append(f"{identifier}: current duty requires an effective date or latest commencement on or before the audit date")
        if entry["status"] == "future" and latest_commencement and latest_commencement <= audit_date:
            errors.append(f"{identifier}: future duty has an effective date or latest commencement on or before the audit date")

    for finding in record["findings"]:
        identifier = finding["id"]
        evidence = references(finding, "evidence_ids", "evidence")
        sources = references(finding, "legal_ids", "legal_ledger")
        evidence_status = finding["evidence_status"]
        applicability = finding["applicability"]
        legal_status = finding["legal_status"]
        if evidence_status in {"observed_gap", "meets_sampled_check", "not_applicable"}:
            if not has_direct_evidence(evidence):
                errors.append(f"{identifier}: {evidence_status} requires direct evidence")
        if (evidence_status == "not_applicable") != (applicability == "not_applicable"):
            errors.append(f"{identifier}: not_applicable requires matching evidence and applicability statuses")
        source_statuses = {source["status"] for source in sources}
        if legal_status != "good_practice" and source_statuses != {legal_status}:
            errors.append(f"{identifier}: {legal_status} requires ledger entries with the same status")
        if legal_status == "good_practice" and sources:
            errors.append(f"{identifier}: good_practice cannot cite binding duties as its classification")

    dependencies = {}
    findings_with_actions = set()
    for action in record["actions"]:
        identifier = action["id"]
        findings = references(action, "finding_ids", "findings")
        findings_with_actions.update(action["finding_ids"])
        prerequisites = references(action, "dependencies", "actions")
        if action["kind"] == "remediation" and any(
            finding["evidence_status"] == "not_verified" for finding in findings
        ):
            errors.append(f"{identifier}: not_verified findings require an evidence request")
        dependencies[identifier] = action["dependencies"]
        evidence = references(action, "verification_evidence_ids", "evidence")
        matching_evidence = [
            item for item in evidence
            if EVIDENCE_MODES.get(item["kind"]) == action["verification_mode"]
        ]
        if action["verification_status"] == "verified":
            if not has_direct_evidence(matching_evidence):
                errors.append(f"{identifier}: verified action requires direct verification evidence in its verification mode")
            if any(item["verification_status"] != "verified" for item in prerequisites):
                errors.append(f"{identifier}: verified action has an unverified dependency")
            baseline_ids = {
                evidence_id
                for finding in findings
                if finding["evidence_status"] in {"observed_gap", "not_verified"}
                for evidence_id in finding["evidence_ids"]
            }
            baseline_evidence = [
                indexes["evidence"][evidence_id] for evidence_id in baseline_ids
                if evidence_id in indexes["evidence"]
            ]
            if baseline_evidence:
                last_observation = max(map(capture_time, baseline_evidence))
                if not any(
                    item["status"] == "direct" and capture_time(item) > last_observation
                    for item in matching_evidence
                ):
                    errors.append(f"{identifier}: verification must be newer than the baseline evidence")

    for finding in record["findings"]:
        if finding["evidence_status"] in {"observed_gap", "not_verified"} and finding["id"] not in findings_with_actions:
            errors.append(f"{finding['id']}: {finding['evidence_status']} finding requires a linked action")

    try:
        TopologicalSorter(dependencies).prepare()
    except CycleError as error:
        errors.append("action dependency cycle: " + " -> ".join(error.args[1]))
    return errors


def markdown(text):
    """Keep data in literal text, including under Markdown extensions."""
    text = " ".join(str(text).split())
    return "".join(
        char if char.isalnum() or char == " " else
        f"&#{ord(char)};" if char.isprintable() else
        ""
        for char in text
    )


def render(record):
    lines = [
        "# India DPDP audit",
        "",
        "Technical and readiness review within the recorded scope. Confirm legal applicability, exemptions, and deadlines with qualified Indian counsel.",
        "",
        f"**Subject** {markdown(record['scope']['subject'])}",
        f"**Audit date** {markdown(record['audit_date'])}",
    ]

    def field(label, value):
        lines.append(f"- **{label}** {markdown(value)}")

    def values(label, items, empty="None recorded"):
        field(label, "; ".join(items) if items else empty)

    def heading(title, items):
        lines.extend(("", f"## {title}", ""))
        if not items:
            lines.append("None recorded.")

    def entry(item, title=None):
        label = markdown(item["id"])
        if title:
            label += " — " + markdown(title)
        lines.extend(("", f"### {label}", ""))

    scope = record["scope"]
    heading("Scope", scope)
    values("Authorized domains", scope["authorized_domains"])
    values("Modes", scope["modes"])
    values("Platforms", scope["platforms"])
    values("Authorized repositories", [
        item["locator"] + " @ " + item["revision"]
        for item in scope.get("authorized_repositories", [])
    ])
    for limitation in scope["limitations"]:
        field("Limitation", limitation)

    heading("Findings", record["findings"])
    priority = {"high": 0, "medium": 1, "low": 2, "informational": 3}
    for finding in sorted(record["findings"], key=lambda item: priority[item["priority"]]):
        entry(finding, finding["title"])
        field("Priority", finding["priority"])
        field("Confidence", finding["confidence"])
        field("Evidence status", finding["evidence_status"].replace("_", " "))
        field("Applicability", finding["applicability"].replace("_", " "))
        field("Applicability reasoning", finding["applicability_reason"])
        field("Legal status", finding["legal_status"].replace("_", " "))
        field("Observation", finding["observation"])
        values("Evidence IDs", finding["evidence_ids"])
        values("Legal IDs", finding["legal_ids"])

    heading("Actions", record["actions"])
    for action in record["actions"]:
        entry(action, action["summary"])
        field("Kind", action["kind"].replace("_", " "))
        field("Owner role", action["owner_role"])
        field("Target", action["target"])
        field("Effort", action["effort"])
        values("Finding IDs", action["finding_ids"])
        values("Dependencies", action["dependencies"])
        for criterion in action["acceptance_criteria"]:
            field("Acceptance criterion", criterion)
        for step in action["verification_steps"]:
            field("Verification step", step)
        field("Verification mode", action["verification_mode"])
        field("Verification status", action["verification_status"])
        values("Verification evidence IDs", action["verification_evidence_ids"])

    heading("Journey coverage", record["coverage"])
    for journey in record["coverage"]:
        entry(journey, journey["name"])
        field("Status", journey["status"].replace("_", " "))
        field("Notes", journey["notes"])
        values("Evidence IDs", journey["evidence_ids"])

    heading("Data map", record["data_map"])
    for flow in record["data_map"]:
        entry(flow)
        field("Journey ID", flow["journey_id"])
        values("Observed facts", flow["observed_facts"])
        values("Observation evidence IDs", flow["evidence_ids"])
        if not flow["owner_claims"]:
            field("Owner claims", "None recorded")
        for claim in flow["owner_claims"]:
            field("Owner-asserted purpose", claim["purpose"])
            field("Owner-asserted ground", claim["claimed_ground"])
            values("Owner statement IDs", claim["evidence_ids"])
        values("Unknowns", flow["unknowns"])

    heading("Legal ledger", record["legal_ledger"])
    for source in record["legal_ledger"]:
        entry(source, source["instrument"] + " — " + source["provision"])
        field("Official source", source["source_url"])
        field("Verified on", source["verified_on"])
        field("Published on", source["published_on"] or "Unknown")
        field("Effective on", source["effective_on"] or "Unresolved or not recorded")
        if "effective_by" in source:
            field("Effective by (latest supported date)", source["effective_by"])
        if "preparation_on" in source:
            field("Preparation date", source["preparation_on"])
        field("Status at audit date", source["status"])
        field("Notes", source["notes"])

    heading("Evidence register", record["evidence"])
    for evidence in record["evidence"]:
        entry(evidence)
        field("Kind", evidence["kind"].replace("_", " "))
        field("Evidence status", evidence["status"])
        field("Captured at", evidence["captured_at"])
        field("Locator", evidence["locator"])
        if "repository" in evidence:
            field("Repository and revision", evidence["repository"] + " @ " + evidence["revision"])
        field("Observation", evidence["observation"])
    return "\n".join(lines) + "\n"


def diff(before, after):
    """List record differences by stable ID without inferring closure."""
    result = {}
    for key in ("audit_date", "scope"):
        if before[key] != after[key]:
            fields = ["value"] if key == "audit_date" else sorted(
                field for field in before[key].keys() | after[key].keys()
                if before[key].get(field) != after[key].get(field)
            )
            result[key] = fields

    for key in COLLECTIONS:
        old = {item["id"]: item for item in before[key]}
        new = {item["id"]: item for item in after[key]}
        changed = {}
        for identifier in sorted(old.keys() & new.keys()):
            previous, current = old[identifier], new[identifier]
            if previous != current:
                changed[identifier] = sorted(
                    field for field in previous.keys() | current.keys()
                    if previous.get(field) != current.get(field)
                )
        added = sorted(new.keys() - old.keys())
        removed = sorted(old.keys() - new.keys())
        if added or removed or changed:
            result[key] = {"added": added, "removed": removed, "changed": changed}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "render", "diff"):
        subparser = commands.add_parser(command)
        subparser.add_argument("audit", type=Path)
        if command == "diff":
            subparser.add_argument("later_audit", type=Path)
    args = parser.parse_args(argv)

    paths = [args.audit, args.later_audit] if args.command == "diff" else [args.audit]
    records = []
    try:
        validator = schema_validator()
        for path in paths:
            record = read_json(path)
            errors = validate(record, validator)
            if errors:
                for error in errors:
                    print(f"{path}: {error}", file=sys.stderr)
                return 1
            records.append(record)
    except (OSError, ValueError, OverflowError, RecursionError) as error:
        print(error, file=sys.stderr)
        return 1

    if args.command == "render":
        print(render(records[0]), end="")
    elif args.command == "diff":
        print(json.dumps(diff(*records), indent=2))
    else:
        print("Audit record is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
