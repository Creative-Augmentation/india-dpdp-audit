"""Offline commencement consistency checks for pinned DPDP notifications.

Recognizes English, citation-only provision lists. Supported examples include
"Rules 1 and 3", "r. 4", "Sections 3–5", and "Section 27(1)(d)". Delimiters
include commas, semicolons, "and", and "&". Ranges span whole numbered
provisions. Descriptive prose and subsection ranges require separate ledger
entries with citation-only provision fields. Subsections of provisions
pinned as a whole inherit the phase of the parent. This checks the commencement
window, without determining substantive applicability or verifying new law.
"""

from datetime import date
import json
from pathlib import Path
import re


_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "assets/legal-phases.json"
_REGISTRY = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
_DPDP_NAME = r"(?:d\.?\s*p\.?\s*d\.?\s*p\.?|digital personal data protection)"
_DPDP = re.compile(rf"\b{_DPDP_NAME}\b", re.I)
_GSR = r"g\.?\s*s\.?\s*r\.?\s*"
_INSTRUMENT = {
    "act": re.compile(rf"\b(?:{_DPDP_NAME}\s+(?:\(dpdp\)\s+)?act|{_GSR}843)\b", re.I),
    "rules": re.compile(rf"\b(?:{_DPDP_NAME}\s+(?:\(dpdp\)\s+)?rules|{_GSR}846)\b", re.I),
}
_SOURCE = {
    _REGISTRY["act"]["act_url"]: "act",
    _REGISTRY["act"]["source_url"]: "act",
    _REGISTRY["rules"]["source_url"]: "rules",
    _REGISTRY["rules"]["corrigendum_url"]: "rules",
}
_CITATION = re.compile(
    r"(?:(?P<kind>rules?|rr?\.|sections?|secs?\.?|ss?\.)\s*)?"
    r"(?P<number>[1-9][0-9]?)(?P<parts>(?:\s*\(\s*[a-z0-9]+\s*\))*)"
    r"(?:\s*(?:[-–—]|\bto\b)\s*(?P<end>[1-9][0-9]?))?",
    re.I,
)
_SEPARATOR = re.compile(r"\s*(?:[,;&]\s*(?:and\b)?|\band\b)\s*", re.I)


def _whole_phases(instrument):
    result = {}
    for phase, provisions in _REGISTRY[instrument]["whole_provisions"].items():
        for provision in provisions:
            start, *end = provision.split("-")
            for number in range(int(start), int(end[0] if end else start) + 1):
                result[number] = phase
    return result


_WHOLE = {instrument: _whole_phases(instrument) for instrument in ("act", "rules")}


def _provision_phases(kind, number, parts):
    phase = _WHOLE[kind].get(number)
    if phase:
        return {phase}, False
    split = _REGISTRY[kind]["split_provisions"].get(str(number), {})
    if parts in split:
        return {split[parts]}, False
    if kind == "act" and number == 27 and parts == "(1)":
        return {value for reference, value in split.items() if reference.startswith("(1)")}, False
    if not parts and number != 1 and split:
        return set(split.values()), False
    return set(), True


def _classify(entry):
    instrument = entry["instrument"]
    source = _SOURCE.get(re.split(r"[?#]", entry.get("source_url", ""), maxsplit=1)[0])
    instruments = {kind for kind, pattern in _INSTRUMENT.items() if pattern.search(instrument)}
    if not instruments and not source:
        return set(), bool(_DPDP.search(instrument))
    if re.search(r"\bdraft\b", instrument, re.I) or (source and instruments and source not in instruments):
        return set(), True
    if source:
        instruments.add(source)
    kind = next(iter(instruments)) if len(instruments) == 1 else None
    phases = set()
    unmapped = False
    for term in _SEPARATOR.split(entry["provision"].strip()):
        match = _CITATION.fullmatch(term)
        if not match:
            unmapped = True
            continue
        explicit, number, parts, end = match.groups()
        if explicit:
            kind = "rules" if explicit.lower().startswith("r") else "act"
        if kind not in instruments:
            unmapped = True
            continue
        start, stop = int(number), int(end or number)
        if stop < start or (end and parts):
            unmapped = True
            continue
        for provision in range(start, stop + 1):
            mapped, unknown = _provision_phases(kind, provision, "".join(parts.lower().split()))
            phases.update(mapped)
            unmapped |= unknown
    return phases, unmapped


def entry_warnings(entry):
    """Return a warning for DPDP text outside the pinned citation map."""
    _, unmapped = _classify(entry)
    if not unmapped:
        return []
    return [f'{entry["id"]}: DPDP commencement citation is wholly or partly unmapped. '
            'Check the official source and use citation-only provisions.']


def check_entry(entry, audit_date):
    """Return consistency errors for a schema-valid legal ledger entry."""
    phases, unmapped = _classify(entry)
    if not phases and not unmapped:
        return []
    identifier = entry["id"]
    status = entry["status"]
    effective_on, effective_by = entry.get("effective_on"), entry.get("effective_by")
    if len(phases) != 1 or unmapped:
        reason = "has an unmapped DPDP provision" if unmapped else "spans multiple DPDP commencement phases"
        if status != "uncertain" or effective_on or effective_by:
            return [f"{identifier}: {reason}. Split the citations into dated entries "
                    "or retain an uncertain entry without a single commencement date."]
        return []

    phase = next(iter(phases))
    bounds = _REGISTRY["windows"][phase]
    earliest, latest = bounds["earliest"], bounds["latest"]
    audit_day = audit_date.isoformat() if isinstance(audit_date, date) else audit_date
    errors = []
    if effective_on and not earliest <= effective_on <= latest:
        errors.append(f"{identifier}: effective_on contradicts pinned DPDP commencement window "
                      f"{earliest} through {latest}")
    if effective_by and effective_by != latest:
        errors.append(f"{identifier}: effective_by must equal pinned DPDP latest commencement {latest}")
    if earliest <= audit_day < latest and status != "uncertain":
        errors.append(f"{identifier}: DPDP commencement is uncertain on the audit date "
                      f"within the pinned {earliest} through {latest} window")
    elif status == "current" and audit_day < latest:
        errors.append(f"{identifier}: DPDP provision cannot be current before {latest}")
    elif status == "future" and audit_day >= latest:
        errors.append(f"{identifier}: DPDP provision cannot be future on or after {latest}")
    return errors
