"""Summarize the audit record and its bounded browser sample."""

from collector.audit_record import PHASES


def render_summary(evidence: dict, audit_record: dict) -> tuple[str, bool]:
    actions = {
        finding_id: action["summary"]
        for action in audit_record["actions"] for finding_id in action["finding_ids"]
    }
    gaps = []
    questions = []
    for finding in audit_record["findings"]:
        line = f"- **{finding['title']}.** {finding['observation']} {actions[finding['id']]}"
        if finding["evidence_status"] == "observed_gap":
            evidence_ids = ", ".join(finding["evidence_ids"])
            gaps.append(f"{line} Evidence `{evidence_ids}`.")
        elif finding["evidence_status"] == "not_verified":
            questions.append(line)

    samples = []
    for observed in evidence.get("observations", ()):
        if observed["status"] in {"observed", "partial"}:
            label = PHASES[observed["phase"]]
            forms = observed.get("forms") or []
            fields = sum(len(form.get("fields") or []) for form in forms)
            requests = observed.get("requests") or []
            blocked = sum(request.get("disposition") == "blocked" for request in requests)
            samples.append(
                f"- **{label}.** {len(forms)} sampled forms, {fields} sampled fields, "
                f"{len(requests)} recorded requests, {blocked} marked blocked."
            )

    lines = ["# Website evidence summary", ""]
    if gaps:
        lines.extend(["## Observed gaps", "", *gaps, ""])
    lines.extend(["## Open questions", "", *questions, "", "## Browser sample", ""])
    lines.extend(samples or ["The collector produced no usable sample."])
    lines.extend([
        "",
        f"The sampling window is {evidence.get('settle_ms', 500)} ms after DOMContentLoaded "
        "or the selected button click. Activity may occur after a quiet sample.",
        "",
        "Use a controlled environment to verify features affected by blocked requests. "
        "This sample supplies evidence for review and leaves legal applicability and conclusions open.",
        "",
    ])
    return "\n".join(lines), bool(samples)
