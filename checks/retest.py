"""Re-evaluate one check after evidence has been recollected."""

from .contract import Check, CheckResult
from .evidence import EvidenceBundle


def retest(check: Check, previous_result: CheckResult, new_bundle: EvidenceBundle) -> str:
    """Close an earlier gap when the recollected evidence supports an ok result."""
    result = check.run(new_bundle)
    if result.status == "gap":
        return "still_failing"
    if previous_result.status == "gap" and result.status == "ok":
        return "closed"
    return "could_not_check"
