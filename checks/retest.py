"""Re-evaluate one check after evidence has been recollected."""

from .contract import Check, CheckResult
from .evidence import EvidenceBundle


def retest(check: Check, previous_result: CheckResult, new_bundle: EvidenceBundle) -> str:
    result = check.run(new_bundle)
    if result.status == "gap":
        return "still_failing"
    if result.status == "ok" and set(result.evidence_refs).difference(previous_result.evidence_refs):
        return "closed"
    return "could_not_check"
