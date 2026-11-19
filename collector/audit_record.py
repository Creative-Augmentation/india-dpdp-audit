"""Translate a redacted browser packet into the foundation audit record."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


PHASES = {
    "entry": "Entry page",
    "initial": "Initial consent page",
    "reject": "After rejection",
    "revisit_after_reject": "Revisit after rejection",
    "initial_before_accept": "Initial consent page before acceptance",
    "accept": "After acceptance",
    "revisit_after_accept": "Revisit after acceptance",
    "withdraw": "After withdrawal",
    "revisit_after_withdraw": "Revisit after withdrawal",
}
AUDIT_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def browser_facts(observation):
    facts = []
    unlabeled = 0
    if observation.get("document_evidence_status") == "observed":
        forms = observation["forms"]
        fields = [field for form in forms for field in form["fields"]]
        facts.append(f"Chromium sampled {len(forms)} forms and {len(fields)} visible fields.")
        unlabeled = sum(field.get("missing_label") is True for field in fields)
        if unlabeled:
            facts.append(f"Chromium sampled {unlabeled} visible text-entry fields without a label.")
    if observation.get("page_response_evidence_status") == "observed":
        facts.append(f"The sampled page returned HTTP {observation['page_status']}.")
    requests = observation.get("requests", ())
    attempts = sum(item.get("attempt_evidence_status") == "observed" for item in requests)
    responses = sum(item.get("response_evidence_status") == "observed" for item in requests)
    if attempts or responses:
        facts.append(f"The browser attempted {attempts} requests and the collector received {responses} responses.")
    for name, status in observation.get("storage_evidence_status", {}).items():
        if status == "observed":
            facts.append(f"The sampled {name} entry count was {observation['storage'][name]}.")
    return facts, unlabeled


def build_audit_record(packet):
    """Build a record for audit.py validate from one collection run."""
    origin = packet["authorized_origin"]
    captured_at = packet.get("finished_at") or datetime.now(timezone.utc).isoformat()
    audit_date = datetime.fromisoformat(captured_at).astimezone(AUDIT_TIMEZONE).date()
    record = {
        "schema_version": "1.0",
        "audit_date": audit_date.isoformat(),
        "scope": {
            "subject": "Authorized website browser sample",
            "authorized_domains": [urlsplit(origin).hostname],
            "modes": ["public"],
            "platforms": ["Chromium"],
            "limitations": [
                "The run sampled selected phases in isolated contexts. Third-party delivery and form submission were outside scope."
            ],
        },
        "coverage": [], "evidence": [], "data_map": [], "legal_ledger": [], "findings": [], "actions": [],
    }

    def finding(key, title, observation, next_step, evidence_ids, *, gap=False, mode="public"):
        identifier = f"F-{key}"
        record["findings"].append({
            "id": identifier, "title": title, "observation": observation,
            "priority": "low" if gap else "informational",
            "confidence": "high" if gap else "low",
            "evidence_status": "observed_gap" if gap else "not_verified",
            "applicability": "applicable" if gap else "unknown",
            "applicability_reason": "This is a structural check of the sampled fields." if gap else
            "Applicability depends on evidence outside the completed browser checks.",
            "legal_status": "good_practice", "evidence_ids": evidence_ids, "legal_ids": [],
        })
        record["actions"].append({
            "id": f"A-{key}", "kind": "remediation" if gap else "evidence_request", "summary": next_step,
            "owner_role": "Website owner", "target": title, "effort": "One targeted follow-up",
            "finding_ids": [identifier], "dependencies": [],
            "acceptance_criteria": ["Each sampled field has a descriptive label." if gap else
                                    "The additional evidence addresses the open question."],
            "verification_steps": [next_step], "verification_mode": mode,
            "verification_status": "pending", "verification_evidence_ids": [],
        })

    for phase in packet.get("observations", ()):
        key = phase["phase"]
        label = PHASES[key]
        facts, unlabeled = browser_facts(phase)
        evidence_ids = []
        if facts:
            identifier = f"E-{key}"
            evidence_ids.append(identifier)
            record["evidence"].append({
                "id": identifier, "kind": "public_browser", "status": "direct",
                "captured_at": captured_at, "locator": origin, "observation": " ".join(facts),
            })

        status = phase["status"]
        notes = "The selected browser phase was sampled within its configured window."
        coverage = "inspected"
        if status != "observed" or not evidence_ids:
            coverage = "not_inspected" if status == "not_attempted" else "blocked"
            reasons = phase.get("reasons", ())
            notes = "Could not verify the complete browser phase in this run."
            next_step = "Obtain authorized access or the missing resources and repeat this phase."
            if "page_resources_incomplete" in reasons:
                notes = "Could not verify tracking after the choice because delivery of page resources was incomplete."
            elif "action_not_configured" in reasons:
                notes = "Could not verify this phase because its consent interaction was not configured."
                next_step = "Confirm authorization, then supply a selector for the consent interaction and rerun."
            elif "playwright_dependency_unavailable" in reasons or "browser_unavailable" in reasons:
                next_step = "Check the Playwright and Chromium installation, then repeat this phase."
            finding(key, label, notes, next_step, evidence_ids)
        record["coverage"].append({
            "id": f"J-{key}", "name": label, "status": coverage, "notes": notes, "evidence_ids": evidence_ids,
        })
        if any(notice.get("evidence_status") == "unknown" for notice in phase.get("notices", ())):
            finding(f"notice-{key}", f"{label} notice", "Could not verify all configured notices in the sample.",
                    "Supply the notice location and verify that it is visible in this phase.", [])
        if unlabeled:
            finding(f"label-{key}", f"Unlabeled text-entry fields in {label.lower()}",
                    f"Chromium sampled {unlabeled} visible text-entry fields without a label.",
                    "Provide descriptive labels and repeat the sampled browser check.", evidence_ids, gap=True)

    if packet.get("merchant_status") == "collection-error":
        finding("setup", "Browser collection", "Could not verify any phase because collection stopped during setup.",
                "Check the collector setup and supplied scope, then repeat the collection.", [])
    attestation = packet.get("authorization", {})
    if attestation.get("evidence_status") == "supplied":
        record["evidence"].append({
            "id": "E-authorization", "kind": "owner_statement", "status": "asserted",
            "captured_at": attestation["attested_at"], "locator": "Collection authorization attestation",
            "observation": "The operator attested that the origin and selected interactions were authorized.",
        })
        finding("authorization", "Authorization scope", "Could not verify the supplied authorization independently.",
                "Confirm the origin and interactions against the written authorization.", ["E-authorization"],
                mode="internal")
    finding("purpose", "Purpose and consent", "Could not verify processing purposes or actual third-party delivery.",
            "Compare sampled forms with purpose notices and verify processing before and after each choice.", [],
            mode="internal")
    finding("controls", "Internal controls", "Could not verify controls that require internal records.",
            "Request redacted records for consent, retention, rights handling, vendors and incident procedures.", [],
            mode="internal")
    return record
