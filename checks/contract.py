"""The evidence, result and remediation contract for platform checks."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re

from .evidence import ARTIFACT_NAME, EvidenceBundle, _segments, is_evidence_ref


STACKS = ("shopify", "woocommerce", "generic")
LEGAL_PHASES = Path(__file__).resolve().parents[1] / "skills/india-dpdp-audit/assets/legal-phases.json"


@lru_cache(maxsize=1)
def _rule_phases():
    registry = json.loads(LEGAL_PHASES.read_text(encoding="utf-8"))
    citations = {}
    for phase, ranges in registry["rules"]["whole_provisions"].items():
        for item in ranges:
            first, _, last = item.partition("-")
            for number in range(int(first), int(last or first) + 1):
                citations[f"Rule {number}"] = registry["windows"][phase]
    return registry["rules"]["source_url"], citations


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _items(values, item_type):
    if isinstance(values, str):
        raise ValueError("Expected a sequence of values.")
    values = tuple(values)
    if any(not isinstance(value, item_type) or (item_type is str and not _text(value)) for value in values):
        raise ValueError("Invalid value in sequence.")
    return values


@dataclass(frozen=True)
class Basis:
    kind: str
    citation: str | None = None
    note: str | None = None

    def __post_init__(self):
        if self.kind == "legal" and isinstance(self.citation, str) and self.citation in _rule_phases()[1]:
            return
        if self.kind == "good_practice" and _text(self.note) and self.citation is None:
            return
        raise ValueError("Use a pinned DPDP rule citation or a good-practice note.")


@dataclass(frozen=True)
class Need:
    """A named collector phase or artifact, optionally with a required JSON field."""

    kind: str
    name: str
    pointer: str = ""

    def __post_init__(self):
        if self.kind not in ("packet", "artifact") or not _text(self.name):
            raise ValueError("A need must name a packet phase or artifact.")
        if self.kind == "artifact" and not ARTIFACT_NAME.fullmatch(self.name):
            raise ValueError("Invalid artifact name.")
        if not isinstance(self.pointer, str):
            raise ValueError("A need's JSON pointer must be a string.")
        _segments(self.pointer)

    def describe(self):
        source = "Collector phase" if self.kind == "packet" else "Artifact"
        return f"{source} {self.name}{self.pointer}"


@dataclass(frozen=True)
class Retest:
    recollect: tuple[Need, ...]
    closes_when: str

    def __post_init__(self):
        object.__setattr__(self, "recollect", _items(self.recollect, Need))
        if not self.recollect or not _text(self.closes_when):
            raise ValueError("A retest needs evidence to recollect and a closure condition.")


@dataclass(frozen=True)
class Fix:
    target: str
    responsible_role: str
    summary: str
    acceptance_test: str
    retest: Retest

    def __post_init__(self):
        if not all(map(_text, (self.target, self.responsible_role, self.summary, self.acceptance_test))):
            raise ValueError("A fix needs a target, responsible role, summary and acceptance test.")
        if not isinstance(self.retest, Retest):
            raise ValueError("A fix needs a retest.")


@dataclass(frozen=True)
class CheckResult:
    status: str
    observation: str
    evidence_refs: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    fix: Fix | None = None
    evidence_request: str | None = None

    def __post_init__(self):
        if self.status not in ("gap", "ok", "could_not_check") or not _text(self.observation):
            raise ValueError("A check result needs a supported status and an observation.")
        refs = _items(self.evidence_refs, str)
        if any(not is_evidence_ref(ref) for ref in refs):
            raise ValueError("Use packet observation or artifact evidence references.")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "missing", _items(self.missing, str))
        if self.status == "could_not_check":
            if not self.missing or not _text(self.evidence_request) or self.fix is not None:
                raise ValueError("An unverified result needs missing evidence and an evidence request.")
            return
        if not self.evidence_refs or self.missing or self.evidence_request is not None:
            raise ValueError("A completed result needs evidence references.")
        if self.status == "gap" and not isinstance(self.fix, Fix):
            raise ValueError("A gap needs a fix.")
        if self.status == "ok" and self.fix is not None:
            raise ValueError("Only a gap can include a fix.")


@dataclass(frozen=True)
class Check:
    id: str
    stack: str
    title: str
    basis: Basis
    needs: tuple[Need, ...]
    evaluate: Callable[[EvidenceBundle], CheckResult]

    def __post_init__(self):
        if not _text(self.id) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,61}", self.id):
            raise ValueError("Invalid check ID.")
        if self.stack not in STACKS or not _text(self.title) or not isinstance(self.basis, Basis):
            raise ValueError("A check needs a supported stack, title and basis.")
        if not callable(self.evaluate):
            raise ValueError("A check needs an evaluator.")
        object.__setattr__(self, "needs", _items(self.needs, Need))

    def run(self, evidence: EvidenceBundle) -> CheckResult:
        missing = tuple(need.describe() for need in self.needs if not evidence.has_need(need))
        if missing:
            return CheckResult("could_not_check", "Required evidence was unavailable or incomplete.",
                               missing=missing, evidence_request=f"Supply complete evidence for {', '.join(missing)}.")
        try:
            result = self.evaluate(evidence)
            if isinstance(result, CheckResult):
                valid_ref = evidence.resolves if result.status == "could_not_check" else evidence.supports
                if all(map(valid_ref, result.evidence_refs)):
                    return result
            return CheckResult("could_not_check", "The check did not produce a supported result.",
                               missing=("A result supported by available evidence",),
                               evidence_request="Review the evidence references and rerun this check.")
        except Exception:
            # Exception messages can include data from the supplied artifacts.
            return CheckResult("could_not_check", "The check could not process the supplied evidence.",
                               missing=("A completed evaluation of the supplied evidence",),
                               evidence_request="Confirm the expected input formats and rerun this check.")
