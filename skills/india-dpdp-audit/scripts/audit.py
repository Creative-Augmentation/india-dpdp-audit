"""Validate, render, and compare local India DPDP audit records."""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from graphlib import CycleError, TopologicalSorter
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from textwrap import shorten
from typing import Any
from unicodedata import category, normalize
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "assets" / "audit.schema.json"
LEGAL_PHASES_SPEC = spec_from_file_location("legal_phases", SCRIPT_DIR / "legal_phases.py")
legal_phases = module_from_spec(LEGAL_PHASES_SPEC)
LEGAL_PHASES_SPEC.loader.exec_module(legal_phases)
PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
IMPACT_PRIORITIES = {"critical", "high"}
UNSUPPORTED_CONCLUSION = re.compile(r"(?<![\w-])(?:compl(?:iant|ies|iance)|(?:no|zero)[\s-]+gaps?)\b", re.I)
CONCLUSION_QUALIFIER = re.compile(
    r"\b(?:whether|if|not|un|could\s+not\s+verify)\b(?:[\s-]+\w+){0,3}[\s-]*\Z", re.I
)
EVIDENCE_STATUS_ORDER = {
    "observed_gap": 0, "not_verified": 1, "meets_sampled_check": 2, "not_applicable": 3,
}
MAX_DEFAULT_WINDOW_DAYS = 31
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
    with path.open(encoding="utf-8-sig") as content:
        return json.load(content, object_pairs_hook=unique_object, parse_constant=reject_constant)


def schema_validator():
    schema = read_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    checker = Draft202012Validator.FORMAT_CHECKER
    if not {"date", "date-time"} <= checker.checkers.keys():
        raise ValueError("JSON Schema date/date-time format checkers are missing. Install the skill's scripts/requirements.txt.")
    return Draft202012Validator(schema, format_checker=checker)


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
    captured = datetime.fromisoformat(value)
    if captured.utcoffset() is None:
        raise ValueError("captured_at requires a time zone offset")
    return captured


def has_unsupported_conclusion(text):
    normalized = normalize("NFKC", "".join(char for char in text if category(char) != "Cf"))
    return any(
        not CONCLUSION_QUALIFIER.search(normalized, 0, match.start())
        for match in UNSUPPORTED_CONCLUSION.finditer(normalized)
    )


def check_consistency(record: dict[str, Any]) -> list[str]:
    errors = []
    audit_date = date.fromisoformat(record["audit_date"])
    scope = record["scope"]
    window_start = date.fromisoformat(scope.get("audit_window_start", record["audit_date"]))
    if window_start > audit_date:
        errors.append("scope.audit_window_start is after the audit date")
    if (audit_date - window_start).days + 1 > MAX_DEFAULT_WINDOW_DAYS:
        if "audit_window_reason" not in scope:
            errors.append(f"scope.audit_window_reason is required for an audit window longer than {MAX_DEFAULT_WINDOW_DAYS} days")
        elif not legal_phases.has_explanation(scope["audit_window_reason"]):
            errors.append("scope.audit_window_reason must explain the extended window in at least six distinct words")
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

    def check_open_question(label, *texts):
        if any(has_unsupported_conclusion(text) for text in texts):
            errors.append(f"{label}: unsupported conclusion over an unverified item. State what could not be verified.")

    has_open_questions = not record["coverage"]
    capture_times = {}
    capture_dates = {}
    for evidence in record["evidence"]:
        identifier = evidence["id"]
        check_open_question(identifier, evidence["observation"])
        try:
            captured = capture_time(evidence)
            capture_times[identifier] = captured
            capture_dates[identifier] = captured.astimezone(AUDIT_TIMEZONE).date()
        except (ValueError, OverflowError) as error:
            errors.append(f"{identifier}.captured_at: {error}")
            return errors
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
        if capture_dates[identifier] > audit_date:
            errors.append(f"{identifier}: evidence captured after the audit date")

    for journey in record["coverage"]:
        evidence = references(journey, "evidence_ids", "evidence")
        if journey["status"] == "inspected" and not has_direct_evidence(evidence):
            errors.append(f"{journey['id']}: an inspected journey requires direct evidence")
        if journey["status"] != "inspected":
            has_open_questions = True
            check_open_question(journey["id"], journey["name"], journey["notes"])

    for flow in record["data_map"]:
        identifier = flow["id"]
        if flow["journey_id"] not in indexes["coverage"]:
            errors.append(f"{identifier}.journey_id: unknown coverage ID {flow['journey_id']}")
        evidence = references(flow, "evidence_ids", "evidence")
        if flow["observed_facts"] and not has_direct_evidence(evidence):
            errors.append(f"{identifier}: observed facts require direct evidence")
        if flow["unknowns"]:
            has_open_questions = True
            check_open_question(identifier, *flow["unknowns"])
        for claim in flow["owner_claims"]:
            evidence = references({"id": identifier, **claim}, "evidence_ids", "evidence")
            if any(item["kind"] != "owner_statement" for item in evidence):
                errors.append(f"{identifier}: owner claims require owner_statement evidence")

    for entry in record["legal_ledger"]:
        identifier = entry["id"]
        errors.extend(legal_phases.check_entry(entry, audit_date))
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
        preparation = date.fromisoformat(entry["preparation_on"]) if "preparation_on" in entry else None
        latest_commencement = effective or effective_by
        if entry["status"] == "current" and (latest_commencement is None or latest_commencement > audit_date):
            errors.append(f"{identifier}: current duty requires an effective date or latest commencement on or before the audit date")
        if entry["status"] == "future" and latest_commencement is None and preparation is None:
            errors.append(f"{identifier}: future duty requires effective_on, effective_by, or preparation_on")
        if entry["status"] == "future" and latest_commencement and latest_commencement <= audit_date:
            errors.append(f"{identifier}: future duty has an effective date or latest commencement on or before the audit date")
        if entry["status"] == "future" and preparation and audit_date > preparation and verified <= preparation:
            errors.append(
                f"{identifier}: future duty is past the preparation date. Re-verify against current official sources "
                "or update its status to uncertain or current as supported by the evidence."
            )

    for finding in record["findings"]:
        identifier = finding["id"]
        evidence = references(finding, "evidence_ids", "evidence")
        sources = references(finding, "legal_ids", "legal_ledger")
        evidence_status = finding["evidence_status"]
        applicability = finding["applicability"]
        legal_status = finding["legal_status"]
        direct = has_direct_evidence(evidence)
        if evidence_status == "observed_gap" and not direct:
            errors.append(f"{identifier}: observed_gap requires direct evidence")
        if finding["priority"] in IMPACT_PRIORITIES:
            if not direct:
                errors.append(f"{identifier}: {finding['priority']} priority requires direct evidence")
            elif evidence_status == "not_verified":
                errors.append(f"{identifier}: not_verified findings cannot have high or critical priority")
        if evidence_status == "not_verified":
            has_open_questions = True
            check_open_question(identifier, finding["title"], finding["observation"], finding["applicability_reason"])
        elif applicability == "unknown":
            has_open_questions = True
            check_open_question(identifier, finding["applicability_reason"])
        if evidence_status in {"meets_sampled_check", "not_applicable"}:
            if not evidence or any(item["status"] != "direct" or item["kind"] == "owner_statement" for item in evidence):
                errors.append(f"{identifier}: {evidence_status} requires only direct non-owner evidence")
            if any(capture_dates[item["id"]] < window_start for item in evidence):
                errors.append(f"{identifier}: {evidence_status} requires evidence captured in the audit window")
        if (evidence_status == "not_applicable") != (applicability == "not_applicable"):
            errors.append(f"{identifier}: not_applicable requires matching evidence and applicability statuses")
        source_statuses = {source["status"] for source in sources}
        if legal_status != "good_practice" and source_statuses != {legal_status}:
            errors.append(f"{identifier}: {legal_status} requires ledger entries with the same status")
        if legal_status == "good_practice" and sources:
            errors.append(f"{identifier}: good_practice cannot cite binding duties as its classification")

    if has_open_questions:
        check_open_question("scope.subject", scope["subject"])
        check_open_question("scope.limitations", *scope["limitations"])

    dependencies = {}
    findings_with_actions = set()
    for action in record["actions"]:
        identifier = action["id"]
        findings = references(action, "finding_ids", "findings")
        findings_with_actions.update(action["finding_ids"])
        prerequisites = references(action, "dependencies", "actions")
        if any(finding["evidence_status"] == "not_verified" for finding in findings):
            check_open_question(identifier, action["summary"])
            if action["kind"] == "remediation":
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
                last_observation = max(capture_times[item["id"]] for item in baseline_evidence)
                if not any(
                    item["status"] == "direct" and capture_times[item["id"]] > last_observation
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


AUTOLINK_TOKEN = re.compile(r"@|://|www\.|mailto:|xmpp:", re.IGNORECASE)
BACKTICKS = re.compile(r"`+")


def literal_token(token):
    if AUTOLINK_TOKEN.search(token):
        # Entities and backslash escapes alone do not inhibit GFM autolinks.
        longest = max((len(run) for run in BACKTICKS.findall(token)), default=0)
        fence = "`" * (longest + 1)
        return f"{fence} {token} {fence}"
    return "".join(
        f"&#{ord(char)};" if char in r'&<>"\`*_{}[]|~$#' else char
        for char in token
    )


def markdown(text):
    """Keep data in literal text, including under Markdown extensions."""
    sanitized = "".join(
        char for char in str(text)
        if char in {"\u200c", "\u200d"} or category(char) not in {"Cc", "Cf", "Cs"}
        or char in {"\t", "\n", "\r"}
    )
    return " ".join(literal_token(token) for token in sanitized.split())


def oldest_linked_evidence_date(record):
    entries = [item for collection in ("coverage", "data_map", "findings") for item in record[collection]]
    entries.extend(claim for flow in record["data_map"] for claim in flow["owner_claims"])
    linked = {identifier for item in entries for identifier in item["evidence_ids"]}
    linked.update(
        identifier for action in record["actions"] for identifier in action["verification_evidence_ids"]
    )
    return min(
        (
            capture_time(item).astimezone(AUDIT_TIMEZONE).date()
            for item in record["evidence"] if item["id"] in linked
        ),
        default=None,
    )


def render_summary(record, findings, legal_warning_count):
    """Summarize recorded results within a fixed reading budget."""
    lines = ["", "## Summary", ""]
    groups = {
        status: [finding for finding in findings if finding["evidence_status"] == status]
        for status in ("observed_gap", "not_verified", "meets_sampled_check")
    }
    coverage = record["coverage"]
    blocked = [journey for journey in coverage if journey["status"] == "blocked"]
    uninspected = [journey for journey in coverage if journey["status"] == "not_inspected"]
    missed = blocked + uninspected
    inspected_count = len(coverage) - len(missed)

    def excerpt(value):
        return markdown(shorten(value, width=112, placeholder="…"))

    def preview(items, describe, limit):
        for item in items[:limit]:
            lines.append(f"- {markdown(item['id'])} · {describe(item)}")
        if len(items) > limit:
            lines.append(f"- {len(items) - limit} more in the detailed report.")

    legal_status = {
        "current": "current duty",
        "future": "future duty",
        "uncertain": "legal timing uncertain",
        "good_practice": "good practice",
    }
    applicability = {
        "applicable": "applicable",
        "unknown": "applicability unknown",
        "not_applicable": "not applicable",
    }

    gaps = groups["observed_gap"]
    lines.append(f"**Observed gaps** · {len(gaps)} recorded in the sample.")
    preview(
        gaps,
        lambda item: (
            f"{excerpt(item['title'])} "
            f"({item['priority']} priority, {legal_status[item['legal_status']]}, "
            f"{applicability[item['applicability']]})"
        ),
        3,
    )

    unknowns = groups["not_verified"]
    lines.extend((
        "",
        f"**Could not check** · Unverified findings ({len(unknowns)}), "
        f"journeys without completed inspection ({len(missed)}).",
    ))
    if not coverage:
        lines.append("- No journeys were recorded. There is no recorded journey coverage to assess.")
    elif not inspected_count:
        lines.append("- The record shows no completed journey inspections.")
    preview(unknowns, lambda item: excerpt(item["title"]), 2)
    preview(missed, lambda item: f"{excerpt(item['name'])} ({item['status'].replace('_', ' ')})", 2)
    if legal_warning_count:
        lines.extend(("", f"**Legal phase warnings** · {legal_warning_count}. See the legal ledger."))

    successes = groups["meets_sampled_check"]
    check_label = "check" if len(successes) == 1 else "checks"
    lines.extend(("", f"**Sampled successes** · {len(successes)} recorded {check_label}."))
    preview(successes, lambda item: excerpt(item["title"]), 2)

    scope = record["scope"]
    modes = ", ".join(scope["modes"])
    audit_date = date.fromisoformat(record["audit_date"])
    window_start = date.fromisoformat(scope.get("audit_window_start", record["audit_date"]))
    oldest = oldest_linked_evidence_date(record)
    lines.extend((
        "",
        f"**Scope and coverage** · {modes}. Inspected {inspected_count} of {len(coverage)} recorded journeys "
        f"({len(blocked)} blocked, {len(uninspected)} uninspected).",
        f"Audit window {window_start} through {audit_date} (India dates).",
    ))
    if oldest:
        lines.append(f"Oldest linked evidence date {oldest}.")
    if (audit_date - window_start).days + 1 > MAX_DEFAULT_WINDOW_DAYS:
        lines.append(f"**Extended audit window** · {excerpt(scope['audit_window_reason'])}")
    lines.extend((
        "These results describe the recorded sample only. Overall compliance remains undetermined.",
        "",
        "**Next actions**",
    ))
    finding_order = {item["id"]: index for index, item in enumerate(gaps + unknowns)}
    pending = sorted(
        (action for action in record["actions"] if action["verification_status"] != "verified"),
        key=lambda action: min(
            (finding_order.get(finding_id, len(finding_order)) for finding_id in action["finding_ids"]),
            default=len(finding_order),
        ),
    )
    preview(
        pending,
        lambda item: f"{excerpt(item['summary'])} ({excerpt(item['owner_role'])}, {item['verification_status']})",
        3,
    )
    if not coverage:
        lines.append("- List the collection and data-handling journeys in scope and document what evidence each needs.")
    elif missed:
        lines.append(f"- Obtain the access or evidence in the coverage notes and finish the {len(missed)} outstanding journey inspections.")
    elif not pending:
        lines.append("- Review the scope limitations and obtain evidence for any controls outside the sample.")
    return lines


def render(record):
    lines = [
        "# India DPDP audit",
        "",
        "Technical and readiness review within the recorded scope. This report is not legal advice or a compliance certificate.",
        "",
        f"**Subject** {markdown(record['scope']['subject'])}",
        f"**Audit date** {markdown(record['audit_date'])}",
    ]

    def field(label, value):
        lines.append(f"- **{label}** {markdown(value)}")

    def values(label, items, empty="None recorded"):
        field(label, "; ".join(items) if items else empty)

    def heading(title, items, empty="None recorded."):
        lines.extend(("", f"## {title}", ""))
        if not items:
            lines.append(empty)

    def entry(item, title=None):
        label = markdown(item["id"])
        if title:
            label += " — " + markdown(title)
        lines.extend(("", f"### {label}", ""))

    findings = sorted(
        record["findings"],
        key=lambda item: (EVIDENCE_STATUS_ORDER[item["evidence_status"]], PRIORITY[item["priority"]]),
    )
    ledger = record["legal_ledger"]
    legal_warnings = [legal_phases.entry_warnings(source, record["audit_date"]) for source in ledger]
    lines.extend(render_summary(record, findings, sum(map(len, legal_warnings))))

    scope = record["scope"]
    heading("Scope", scope)
    values("Authorized domains", scope["authorized_domains"])
    values("Modes", scope["modes"])
    values("Platforms", scope["platforms"])
    if "audit_window_start" in scope:
        field("Audit window start", scope["audit_window_start"])
    if "audit_window_reason" in scope:
        field("Audit window reason", scope["audit_window_reason"])
    values("Authorized repositories", [
        item["locator"] + " @ " + item["revision"]
        for item in scope.get("authorized_repositories", [])
    ])
    for limitation in scope["limitations"]:
        field("Limitation", limitation)

    open_findings = [item for item in findings if item["evidence_status"] == "not_verified"]
    missed_journeys = [item for item in record["coverage"] if item["status"] != "inspected"]
    unknown_flows = [item for item in record["data_map"] if item["unknowns"]]
    if open_findings or missed_journeys or unknown_flows:
        lines.extend(("", "## Open questions", ""))
        requests = defaultdict(list)
        for action in record["actions"]:
            if action["kind"] == "evidence_request":
                for finding_id in action["finding_ids"]:
                    requests[finding_id].append(action["summary"])
        inferred_ids = {item["id"] for item in record["evidence"] if item["status"] == "inferred"}
        for finding in open_findings:
            entry(finding, finding["title"])
            field("Could not verify", finding["observation"])
            if inferred_ids.intersection(finding["evidence_ids"]):
                field("Watch", "The linked inference needs direct confirmation.")
            for summary in requests[finding["id"]]:
                field("Next step", summary)
        for journey in missed_journeys:
            entry(journey, journey["name"])
            field("Could not verify", journey["notes"])
            field("Next step", "Obtain authorized access or evidence that addresses the coverage notes and complete the inspection.")
        for flow in unknown_flows:
            entry(flow)
            for question in flow["unknowns"]:
                field("Could not verify", question)
                field("Next step", f"Request a redacted record or authorized check for {flow['journey_id']} that resolves this question.")

    heading("Findings", findings, "No findings were recorded. See the summary for journey coverage and evidence limits.")
    for finding in findings:
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

    heading("Legal ledger", ledger)
    for source, warnings in zip(ledger, legal_warnings):
        entry(source, source["instrument"] + " — " + source["provision"])
        source_url = source["source_url"]
        if warnings and not legal_phases.is_pinned_source(source_url):
            source_url += " (not in pinned official registry)"
        field("Source", source_url)
        field("Verified on", source["verified_on"])
        field("Published on", source["published_on"] or "Unknown")
        field("Effective on", source["effective_on"] or "Unresolved or not recorded")
        if "effective_by" in source:
            field("Effective by (latest supported date)", source["effective_by"])
        if "preparation_on" in source:
            field("Preparation date", source["preparation_on"])
        field("Status at audit date", source["status"])
        field("Notes", source["notes"])
        for warning in warnings:
            field("Legal phase review", warning)

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


UNORDERED_FIELDS = {
    "authorized_domains", "modes", "platforms", "evidence_ids", "legal_ids",
    "finding_ids", "dependencies", "verification_evidence_ids",
}


def comparison_value(value, field=None):
    if isinstance(value, dict):
        return {key: comparison_value(item, key) for key, item in value.items()}
    if isinstance(value, list):
        if field in UNORDERED_FIELDS:
            return sorted(value)
        return [comparison_value(item) for item in value]
    return value


def changed_fields(before, after):
    return sorted(
        field for field in before.keys() | after.keys()
        if comparison_value(before.get(field), field) != comparison_value(after.get(field), field)
    )


def evidence_fingerprint(item):
    return item["kind"], item["locator"], " ".join(item["observation"].split())


def closure_warnings(before, after):
    earlier_date = date.fromisoformat(before["audit_date"])
    earlier_ids = {evidence["id"] for evidence in before["evidence"]}
    earlier_fingerprints = {evidence_fingerprint(item) for item in before["evidence"]}
    followup = [
        evidence for evidence in after["evidence"]
        if evidence["id"] not in earlier_ids
        and evidence["status"] == "direct"
        and evidence["kind"] != "owner_statement"
        and capture_time(evidence).astimezone(AUDIT_TIMEZONE).date() > earlier_date
    ]
    fresh_ids = {item["id"] for item in followup if evidence_fingerprint(item) not in earlier_fingerprints}
    copied_ids = {item["id"] for item in followup} - fresh_ids
    later_findings = {finding["id"]: finding for finding in after["findings"]}
    warnings = []
    for finding in sorted(before["findings"], key=lambda item: item["id"]):
        if finding["evidence_status"] not in {"observed_gap", "not_verified"}:
            continue
        identifier = finding["id"]
        later = later_findings.get(identifier)
        if later is None:
            warnings.append(f"{identifier}: removed finding has no linked follow-up evidence to establish closure.")
        elif later["evidence_status"] in {"meets_sampled_check", "not_applicable"}:
            linked = set(later["evidence_ids"])
            if not fresh_ids.intersection(linked):
                if copied_ids.intersection(linked):
                    warnings.append(
                        f"{identifier}: linked follow-up evidence repeats an earlier kind, locator and observation "
                        "under a new ID and timestamp. Review fresh evidence before treating the finding as closed."
                    )
                else:
                    warnings.append(
                        f"{identifier}: status changed without new linked direct evidence captured after the earlier audit date."
                    )
    return warnings


def diff(before, after):
    """List record differences by stable ID and flag unsupported closure."""
    result = {}
    if before["audit_date"] != after["audit_date"]:
        result["audit_date"] = ["value"]
    scope_fields = changed_fields(before["scope"], after["scope"])
    if scope_fields:
        result["scope"] = scope_fields
    if {"subject", "authorized_domains"}.intersection(scope_fields):
        result["scope_warnings"] = ["Subject or authorized domains changed. Confirm that the two audits are comparable."]

    for key in COLLECTIONS:
        old = {item["id"]: item for item in before[key]}
        new = {item["id"]: item for item in after[key]}
        changed = {}
        for identifier in sorted(old.keys() & new.keys()):
            fields = changed_fields(old[identifier], new[identifier])
            if fields:
                changed[identifier] = fields
        added = sorted(new.keys() - old.keys())
        removed = sorted(old.keys() - new.keys())
        if added or removed or changed:
            result[key] = {"added": added, "removed": removed, "changed": changed}
    warnings = closure_warnings(before, after)
    if warnings:
        result["closure_warnings"] = warnings
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
    except (OSError, ValueError, OverflowError, RecursionError) as error:
        print(f"{SCHEMA_PATH}: {error}", file=sys.stderr)
        return 1
    for path in paths:
        try:
            record = read_json(path)
            errors = validate(record, validator)
        except (OSError, ValueError, OverflowError, RecursionError) as error:
            errors = [str(error)]
        if errors:
            for error in errors:
                print(f"{path}: {error}", file=sys.stderr)
            return 1
        records.append(record)

    if args.command == "render":
        print(render(records[0]), end="")
    elif args.command == "diff":
        print(json.dumps(diff(*records), indent=2))
    else:
        record = records[0]
        for entry in record["legal_ledger"]:
            for warning in legal_phases.entry_warnings(entry, record["audit_date"]):
                print(f"{args.audit}: {warning}", file=sys.stderr)
        print("Audit record is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
