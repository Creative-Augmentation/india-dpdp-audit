"""Translate runner outcomes to the foundation audit record shape."""

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import quote, urlsplit

from .contract import _rule_phases


AUDIT_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def _public_origin(packet):
    origin = packet.get("authorized_origin")
    if not isinstance(origin, str):
        return None, None
    try:
        parts = urlsplit(origin)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return None, None
    if (parts.scheme in {"http", "https"} and parts.username is None and port != 0 and not parts.path
            and not parts.query and not parts.fragment and len(host) <= 253 and DOMAIN.fullmatch(host)):
        return origin, host
    return None, None


def _capture_time(packet, default):
    try:
        value = packet["finished_at"].replace("Z", "+00:00")
        captured = datetime.fromisoformat(value)
        if captured.utcoffset() is not None:
            return captured
    except (KeyError, AttributeError, ValueError):
        pass
    return default


def _rule_entry(citation, audit_date):
    source, rules = _rule_phases()
    earliest, latest = rules[citation]["earliest"], rules[citation]["latest"]
    status = "future" if audit_date < earliest else "current" if audit_date >= latest else "uncertain"
    return {
        "id": "L-DPDP-" + citation.removeprefix("Rule "),
        "instrument": "Digital Personal Data Protection Rules, 2025",
        "provision": citation,
        "source_url": source,
        "verified_on": audit_date,
        "published_on": None,
        "effective_on": latest if earliest == latest else None,
        **({"effective_by": latest} if earliest != latest else {}),
        "status": status,
        "notes": "Commencement comes from the pinned legal phases. The check describes sampled structural evidence.",
    }


def build_audit_record(bundle, outcomes):
    """Build a standalone audit record from run_checks outcomes and their bundle."""
    outcomes = tuple(outcomes)
    packet = bundle.packet or {}
    origin, host = _public_origin(packet)
    now = datetime.now(timezone.utc)
    packet_time = _capture_time(packet, now)
    audit_date = max(now, packet_time).astimezone(AUDIT_TIMEZONE).date().isoformat()
    record = {
        "schema_version": "1.0",
        "audit_date": audit_date,
        "scope": {
            "subject": "Structural checks of supplied evidence",
            "authorized_domains": [host] if host else [],
            "modes": ["public", "internal"] if host else ["internal"],
            "platforms": sorted({item.check.stack for item in outcomes}) or ["generic"],
            "limitations": ["Results describe the supplied samples and their available evidence."],
        },
        "coverage": [], "evidence": [], "data_map": [], "legal_ledger": [], "findings": [], "actions": [],
    }
    legal_entries = {}
    evidence_ids = {}
    for check, result in ((item.check, item.result) for item in outcomes):
        linked_ids = []
        for ref in dict.fromkeys(result.evidence_refs):
            if ref not in evidence_ids:
                if not bundle.resolves(ref):
                    raise ValueError("An audit result references unavailable evidence.")
                identifier = f"E-{len(evidence_ids) + 1}"
                evidence_ids[ref] = identifier
                is_packet = ref.startswith("packet:")
                public = is_packet and origin is not None
                record["evidence"].append({
                    "id": identifier,
                    "kind": "public_browser" if public else "internal_record",
                    "status": "direct" if bundle.supports(ref) else "limited",
                    "captured_at": (packet_time if is_packet else now).isoformat(),
                    "locator": f"{origin}#{quote(ref, safe=':/~')}" if public else ref,
                    "observation": "Referenced content in the supplied structural evidence.",
                })
            linked_ids.append(evidence_ids[ref])

        basis = check.basis
        legal_status, legal_ids = "good_practice", []
        if basis.kind == "legal":
            if basis.citation not in legal_entries:
                legal_entries[basis.citation] = _rule_entry(basis.citation, audit_date)
            entry = legal_entries[basis.citation]
            legal_status, legal_ids = entry["status"], [entry["id"]]

        unverified = result.status == "could_not_check"
        record["coverage"].append({
            "id": f"J-{check.id}", "name": check.title,
            "status": ("blocked" if linked_ids else "not_inspected") if unverified else "inspected",
            "notes": result.observation, "evidence_ids": linked_ids,
        })
        if result.status == "ok":
            continue
        finding = f"F-{check.id}"
        record["findings"].append({
            "id": finding, "title": check.title, "observation": result.observation,
            "priority": "informational" if unverified else "low",
            "confidence": "low" if unverified else "high",
            "evidence_status": "not_verified" if unverified else "observed_gap",
            "applicability": "unknown" if unverified else "applicable",
            "applicability_reason": ("Evidence needed: " + "; ".join(result.missing) if unverified
                                     else basis.note or "The cited rule informs the structural check."),
            "legal_status": legal_status, "evidence_ids": linked_ids, "legal_ids": legal_ids,
        })
        action = {
            "id": f"A-{check.id}", "finding_ids": [finding], "dependencies": [],
            "effort": "One targeted follow-up", "verification_mode": "internal",
            "verification_status": "pending", "verification_evidence_ids": [],
        }
        if unverified:
            action.update(
                kind="evidence_request", summary=result.evidence_request,
                owner_role="Evidence owner", target=check.title,
                acceptance_criteria=list(result.missing), verification_steps=[result.evidence_request],
            )
        else:
            fix = result.fix
            action.update(
                kind="remediation", summary=fix.summary, owner_role=fix.responsible_role, target=fix.target,
                acceptance_criteria=[fix.acceptance_test],
                verification_steps=[f"Recollect {need.describe()}." for need in fix.retest.recollect]
                + [fix.retest.closes_when],
            )
            if host and all(need.kind == "packet" for need in fix.retest.recollect):
                action["verification_mode"] = "public"
        record["actions"].append(action)
    record["legal_ledger"] = list(legal_entries.values())
    return record
