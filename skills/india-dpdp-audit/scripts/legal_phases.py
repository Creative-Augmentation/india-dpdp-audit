"""Offline commencement consistency checks for pinned DPDP notifications.

Recognizes common English and Hindi instrument aliases and citation-only lists. Supported examples include
"Rules 1 and 3", "r. 4", "Sections 3–5", and "Section 27(1)(d)". Delimiters
include commas, semicolons, "and", and "&". Ranges span whole numbered
provisions. Descriptive prose and subsection ranges require separate ledger
entries with citation-only provision fields. Subsections of provisions
pinned as a whole inherit the phase of the parent. This checks the commencement
window, without determining substantive applicability or verifying new law.
An unidentified instrument cited to MeitY, eGazette or India Code requires
uncertain status. The host alone does not determine the instrument family.
Other unidentified sources retain generic date validation and an authority warning.
"""

from datetime import date
import json
from pathlib import Path
import re
from unicodedata import decimal, normalize
from urllib.parse import unquote, urlsplit


_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "assets/legal-phases.json"
_REGISTRY = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
_ACRONYM = r"d\.?\s*p\.?\s*d\.?\s*p\.?(?:\s*[ar]\.?)?(?![a-z])"
_HINDI_NAME = r"डिजिटल\s+(?:वैयक्तिक|व्यक्तिगत)\s+(?:पहचान\s+)?(?:डेटा|डाटा|दत्तांश)\s+संरक्षण"
_NAME = rf"(?:\b{_ACRONYM}|\bdigital\s+personal\s+data\s+protection\b|{_HINDI_NAME})"
_SHORT_ACT = r"\bdata\s+protection\s+act[,\s-]*2023\b"
_ACT_NUMBER = r"\bact\s*(?:no\.?|number)?\s*22\s*of\s*2023\b"
_GSR = r"g\.?\s*s\.?\s*r\.?\s*"
_RULES_OF = re.compile(
    rf"\brules\s+(?:of|under)\s+(?:the\s+)?(?:{_NAME}|{_SHORT_ACT}|{_ACT_NUMBER})", re.I
)
_INSTRUMENT = {
    "act": re.compile(
        rf"(?:\bd\.?\s*p\.?\s*d\.?\s*p\.?\s*a\.?(?![a-z])"
        rf"|{_NAME}\s*(?:\(dpdp\)\s*)?(?:\bact\b|अधिनियम)"
        rf"|{_SHORT_ACT}|{_ACT_NUMBER}|\b{_GSR}843\b|\bs\.?\s*o\.?\s*5458\b)", re.I
    ),
    "rules": re.compile(
        rf"(?:\bd\.?\s*p\.?\s*d\.?\s*p\.?\s*r\.?(?![a-z])"
        rf"|{_NAME}\s*(?:\(dpdp\)\s*)?(?:\brules\b|नियमावली|नियम)"
        rf"|\b{_GSR}(?:846|892)\b)", re.I
    ),
}
_DPDP_HINT = re.compile(rf"(?:{_NAME}|{_SHORT_ACT}|{_ACT_NUMBER})", re.I)
_OFFICIAL_HOSTS = ("meity.gov.in", "egazette.gov.in", "egazette.nic.in",
                   "indiacode.nic.in", "indiacode.gov.in")
_OTHER_INSTRUMENT = re.compile(
    rf"^(?:spdi\s+rules\b|{_GSR}313\b"
    r"|information technology(?:\s+\([^()]+\))?\s+rules\b.*\b2011\b"
    r"|(?:information technology|it)\s+act\b.*\b2000\b"
    r"|cert[ -]in\b.*\b(?:directions?|2022)\b)", re.I
)
_UNCERTAINTY_REASON = re.compile(
    r"\b(?:gazette|publication|source|notification|court|stay|amendment|"
    r"order|corrigendum|conflict|verification|unavailable|inaccessible)\b|अधिसूचना|राजपत्र|न्यायालय|स्रोत", re.I
)
_CITATION = re.compile(
    r"(?:(?P<kind>rules?|rr?\.|sections?|secs?\.?|ss?\.|नियम|धारा|धाराएँ)\s*)?"
    r"(?P<number>[1-9][0-9]?)(?P<parts>(?:\s*\(\s*[a-z0-9]+\s*\))*)"
    r"(?:\s*(?:[-–—]|\bto\b|से)\s*(?P<end>[1-9][0-9]?))?",
    re.I,
)
_SEPARATOR = re.compile(r"\s*(?:[,;&]\s*(?:and\b)?|\band\b| और )\s*", re.I)


def _url_identity(url):
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() != "https":
            return None
        return (parts.hostname or "").rstrip("."), unquote(parts.path).rstrip("/")
    except ValueError:
        return None


_SOURCE = {
    _url_identity(url): kind
    for kind, urls in {
        "act": [*_REGISTRY["act"]["act_urls"], _REGISTRY["act"]["source_url"],
                _REGISTRY["act"]["amendment_url"]],
        "rules": [_REGISTRY["rules"]["source_url"], _REGISTRY["rules"]["corrigendum_url"]],
    }.items()
    for url in urls
}


def _normalized(text):
    return "".join(str(decimal(char, char)) for char in normalize("NFKC", text))


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


def _is_official_host(url_identity):
    if url_identity is None:
        return False
    host, _ = url_identity
    return any(host == name or host.endswith("." + name) for name in _OFFICIAL_HOSTS)


def _classify(entry):
    instrument = _normalized(entry["instrument"])
    provision_text = _normalized(entry["provision"])
    url_identity = _url_identity(entry.get("source_url", ""))
    source = _SOURCE.get(url_identity)
    url_hint = bool(url_identity and _DPDP_HINT.search(url_identity[1].replace("-", " ")))
    if _RULES_OF.search(instrument):
        instruments = {"rules"}
    else:
        instruments = {kind for kind, pattern in _INSTRUMENT.items() if pattern.search(instrument)}
    if not instruments and not source:
        if url_hint or _DPDP_HINT.search(instrument) or _DPDP_HINT.search(provision_text):
            return set(), "unmapped_dpdp"
        if _is_official_host(url_identity) and not _OTHER_INSTRUMENT.search(instrument):
            return set(), "unidentified_official"
        return set(), None
    if re.search(r"\bdraft\b|मसौदा", instrument, re.I) or (source and instruments and source not in instruments):
        return set(), "unmapped_dpdp"
    if source:
        instruments.add(source)
    kind = next(iter(instruments)) if len(instruments) == 1 else None
    phases = set()
    unmapped = False
    for term in _SEPARATOR.split(provision_text.strip()):
        match = _CITATION.fullmatch(term)
        if not match:
            unmapped = True
            continue
        explicit, number, parts, end = match.groups()
        if explicit:
            kind = "rules" if explicit.lower().startswith("r") or explicit == "नियम" else "act"
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
    return phases, "unmapped_dpdp" if unmapped else None


def _audit_day(audit_date):
    return audit_date.isoformat() if isinstance(audit_date, date) else audit_date


def _uncertain_after_latest(entry, audit_date, phases, unmapped):
    if audit_date is None or unmapped or len(phases) != 1 or entry["status"] != "uncertain":
        return False
    latest = _REGISTRY["windows"][next(iter(phases))]["latest"]
    return _audit_day(audit_date) >= latest


def entry_warnings(entry, audit_date=None):
    """Warn about unmapped citations and retained post-commencement uncertainty."""
    phases, unmapped = _classify(entry)
    if unmapped == "unidentified_official":
        return [f'{entry["id"]}: Cannot identify the instrument from the official citation. '
                'Supply its specific title or notification identifier and verify the source.']
    if unmapped:
        return [f'{entry["id"]}: DPDP commencement citation is wholly or partly unmapped. '
                'Check the official source and use citation-only provisions.']
    if _uncertain_after_latest(entry, audit_date, phases, unmapped):
        return [f'{entry["id"]}: DPDP commencement remains uncertain in this record '
                'after the pinned latest commencement. Review the explanation and official sources.']
    if not phases and entry.get("source_url") and not _OTHER_INSTRUMENT.search(_normalized(entry["instrument"])):
        return [f'{entry["id"]}: Instrument authority is unverified by the pinned registry. '
                'Check the cited source and apply the applicable law separately.']
    return []


def check_entry(entry, audit_date):
    """Return consistency errors for a schema-valid legal ledger entry."""
    phases, unmapped = _classify(entry)
    if not phases and not unmapped:
        return []
    identifier = entry["id"]
    status = entry["status"]
    effective_on, effective_by = entry.get("effective_on"), entry.get("effective_by")
    if len(phases) != 1 or unmapped:
        if status != "uncertain" or effective_on or effective_by:
            if unmapped == "unidentified_official":
                return [f"{identifier}: Cannot identify the instrument from the official citation. "
                        "Identify the instrument or retain an uncertain entry without a commencement date."]
            reason = ("has an unmapped DPDP provision" if unmapped
                      else "spans multiple DPDP commencement phases")
            return [f"{identifier}: {reason}. Split the citations into dated entries "
                    "or retain an uncertain entry without a single commencement date."]
        return []

    phase = next(iter(phases))
    bounds = _REGISTRY["windows"][phase]
    earliest, latest = bounds["earliest"], bounds["latest"]
    audit_day = _audit_day(audit_date)
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
    if _uncertain_after_latest(entry, audit_date, phases, unmapped):
        notes = entry.get("notes", "").strip()
        distinct_words = set(re.findall(r"[^\W\d_]+", notes.casefold()))
        if len(distinct_words) < 6 or not _UNCERTAINTY_REASON.search(notes):
            errors.append(f"{identifier}: uncertainty after the latest DPDP commencement requires "
                          "notes explaining the unresolved source or legal issue.")
    return errors
