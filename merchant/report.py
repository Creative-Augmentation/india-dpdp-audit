"""Summarize observed coverage without assuming what a merchant site does."""

PHASES = {
    "entry": "Entry page",
    "initial": "Initial consent page",
    "reject": "After rejection",
    "revisit_after_reject": "Revisit after rejection",
    "accept": "After acceptance",
    "revisit_after_accept": "Revisit after acceptance",
    "withdraw": "After withdrawal",
    "revisit_after_withdraw": "Revisit after withdrawal",
}

COVERAGE_GAPS = {
    "partial": "Partial capture. See the evidence for limitations.",
    "blocked": "Could not check. See the evidence for the capture failure.",
    "not_attempted": "Could not check in this run.",
}


def render_summary(evidence: dict) -> tuple[str, bool]:
    heading = "# Website evidence summary"
    if evidence.get("merchant_status") == "collection-error":
        return (
            f"{heading}\n\n"
            "**Could not check any phase.** The collector failed before producing evidence. "
            "Check collector setup and the supplied scope settings.\n",
            False,
        )

    observations = {
        item["phase"]: item for item in evidence.get("observations", [])
        if item.get("phase") in PHASES
    }
    gaps = []
    samples = []
    for phase, label in PHASES.items():
        if phase == "entry" and phase not in observations:
            continue
        observed = observations.get(phase, {})
        status = observed.get("status")
        if status != "observed":
            gaps.append(f"- **{label}.** {COVERAGE_GAPS.get(status, 'Could not check in this run.')}")
        if status in {"observed", "partial"}:
            forms = observed.get("forms") or []
            fields = sum(len(form.get("fields") or []) for form in forms)
            requests = observed.get("requests") or []
            blocked = sum(request.get("disposition") == "blocked" for request in requests)
            samples.append(
                f"- **{label}.** {len(forms)} sampled forms, {fields} sampled fields, "
                f"{len(requests)} recorded requests, {blocked} marked blocked."
            )

    lines = [heading, "", "## Gaps to verify", ""]
    lines.extend(gaps)
    lines.extend([
        "- **Purpose and consent.** Compare sampled forms with their purpose notices and "
        "confirm actual processing before and after each choice.",
        "- **Internal controls.** Verify consent records where relevant, retention and deletion, "
        "rights handling, vendor arrangements, and incident procedures with the owner.",
        "",
        "## Browser sample",
        "",
    ])
    lines.extend(samples or ["The collector produced no usable sample."])
    lines.extend([
        "",
        "Use a controlled environment to verify features affected by blocked requests. "
        "This sample supplies evidence for review and leaves legal applicability and conclusions open.",
        "",
    ])
    return "\n".join(lines), bool(samples)
