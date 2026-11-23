"""Register checks explicitly and run them in stable ID order."""

from dataclasses import dataclass

from .contract import STACKS, Check, CheckResult
from .evidence import EvidenceBundle
from .stacks import detect_stacks


_CHECKS: dict[str, Check] = {}


@dataclass(frozen=True)
class RunResult:
    check: Check
    result: CheckResult


def register(check: Check) -> Check:
    if check.id in _CHECKS:
        raise ValueError(f"Duplicate check ID {check.id}.")
    _CHECKS[check.id] = check
    return check


def registered_checks() -> tuple[Check, ...]:
    return tuple(_CHECKS[check_id] for check_id in sorted(_CHECKS))


def run_checks(bundle: EvidenceBundle, stacks=None) -> tuple[RunResult, ...]:
    if stacks is None:
        stacks = (entry.stack for entry in detect_stacks(bundle))
    if isinstance(stacks, str):
        stacks = (stacks,)
    selected = set(stacks)
    if not selected.issubset(STACKS):
        raise ValueError("Select shopify, woocommerce or generic.")
    return tuple(RunResult(check, check.run(bundle)) for check in registered_checks() if check.stack in selected)
