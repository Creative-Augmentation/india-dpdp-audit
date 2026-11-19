"""Offline commencement consistency checks for pinned DPDP notifications.

Recognizes common English and Hindi instrument aliases and citation-only lists. Supported examples include
"Rules 1 and 3", "r. 4", "Sections 3–5", and "Section 27(1)(d)". Delimiters
include commas, semicolons, "and", and "&". Ranges span whole numbered
provisions. Descriptive prose and subsection ranges require separate ledger
entries with citation-only provision fields. Subsections of provisions
pinned as a whole inherit the phase of the parent. This checks the commencement
window, without determining substantive applicability or verifying new law.
An unidentified instrument cited to an official host or using a numbered citation
within the DPDP ranges requires uncertain status. The host and numbering alone
do not determine the instrument family.
"""

from datetime import date
import json
from pathlib import Path
import re
from unicodedata import category, decimal, normalize
from urllib.parse import unquote, urlsplit


_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "assets/legal-phases.json"
_REGISTRY = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
_ACRONYM = r"d\.?\s*p\.?\s*d\.?\s*p\.?(?:\s*[ar]\.?)?(?![a-z])"
_HINDI_NAME = r"डिजिटल\s+(?:वैयक्तिक|व्यक्तिगत)\s+(?:पहचान\s+)?(?:डेटा|डाटा|दत्तांश)\s+संरक्षण"
_NAME = rf"(?:\b{_ACRONYM}|\bdigital\s+personal\s+data\s+protection\b|{_HINDI_NAME})"
_SHORT_ACT_TITLE = r"\b(?:personal\s+)?data\s+protection\s+act"
_SHORT_RULES_TITLE = r"\b(?:personal\s+)?data\s+protection\s+rules"
_SHORT_ACT = rf"{_SHORT_ACT_TITLE}[,\s(-]*2023\b"
_SHORT_RULES = rf"{_SHORT_RULES_TITLE}[,\s(-]*2025\b"
_NO_YEAR = r"\b(?![,\s(-]*[0-9]{4}\b)"
_INDIA = re.compile(r"\bindia(?:n)?\b", re.I)
_ACT_NUMBER = r"\bact\s*(?:no\.?|number)?\s*22\s*of\s*2023\b"
_GSR = r"g\.?\s*s\.?\s*r\.?\s*"
_RULES_OF_PREFIX = r"\brules\s+(?:of|under)\s+(?:the\s+)?"
_RULES_OF = re.compile(
    rf"{_RULES_OF_PREFIX}(?:{_NAME}|{_SHORT_ACT}|{_ACT_NUMBER})", re.I
)
_RULES_OF_SHORT_ACT = re.compile(rf"{_RULES_OF_PREFIX}(?:india(?:'s|n)?\s+)?{_SHORT_ACT_TITLE}{_NO_YEAR}", re.I)
_UNDATED_INSTRUMENT = {
    "act": re.compile(rf"{_SHORT_ACT_TITLE}{_NO_YEAR}", re.I),
    "rules": re.compile(rf"{_SHORT_RULES_TITLE}{_NO_YEAR}", re.I),
}
_INSTRUMENT = {
    "act": re.compile(
        rf"(?:\bd\.?\s*p\.?\s*d\.?\s*p\.?\s*a\.?(?![a-z])"
        rf"|{_NAME}\s*(?:\(dpdp\)\s*)?(?:\bact\b|अधिनियम)"
        rf"|{_SHORT_ACT}|{_ACT_NUMBER}|\b{_GSR}843\b|\bs\.?\s*o\.?\s*5458\b)", re.I
    ),
    "rules": re.compile(
        rf"(?:\bd\.?\s*p\.?\s*d\.?\s*p\.?\s*r\.?(?![a-z])"
        rf"|{_NAME}\s*(?:\(dpdp\)\s*)?(?:\brules\b|नियमावली|नियम)"
        rf"|{_SHORT_RULES}|\b{_GSR}(?:846|892)\b)", re.I
    ),
}
_DPDP_HINT = re.compile(rf"(?:{_NAME}|{_SHORT_ACT}|{_SHORT_RULES}|{_ACT_NUMBER})", re.I)
_OFFICIAL_HOSTS = ("meity.gov.in", "meity.nic.in", "egazette.gov.in", "egazette.nic.in",
                   "indiacode.gov.in", "indiacode.nic.in", "pib.gov.in", "pib.nic.in")
_OTHER_INSTRUMENT = re.compile(
    rf"^(?:spdi\s+rules\b|{_GSR}313\b"
    r"|information technology(?:\s+\([^()]+\))?\s+rules\b.*\b2011\b"
    r"|(?:information technology|it)\s+act\b.*\b2000\b"
    r"|cert[ -]in\b.*\b(?:directions?|2022)\b"
    r"|consumer protection\s*\(e[ -]commerce\)\s*rules[,\s-]*2020\b"
    r"|consumer protection act[,\s-]*2019\b"
    r"|(?:payment and settlement systems|pss) act[,\s-]*2007\b"
    r"|legal metrology(?:\s*\(packaged commodities\))?\s+rules[,\s-]*2011\b"
    rf"|(?:(?:uk|united kingdom)\s+)?{_SHORT_ACT_TITLE}[,\s(-]*2018\b"
    rf"|(?:singapore\s+)?{_SHORT_ACT_TITLE}[,\s(-]*2012\b)", re.I
)
_UNCERTAINTY_REASON = re.compile(
    r"\b(?:gazette|publication|source|notification|court|stay|amendment|"
    r"order|corrigendum|conflict|verification|unavailable|inaccessible)\b|अधिसूचना|राजपत्र|न्यायालय|स्रोत", re.I
)
_CITATION_LABEL = r"rules?|rr?\.|sections?|secs?\.?|ss?\.|नियम|धारा|धाराएँ"
_CITATION = re.compile(
    rf"(?:(?P<kind>{_CITATION_LABEL})\s*)?"
    r"(?P<number>[1-9][0-9]?)(?P<parts>(?:\s*\(\s*[a-z0-9]+\s*\))*)"
    r"(?:\s*(?:[-–—]|\bto\b|से)\s*(?P<end>[1-9][0-9]?))?",
    re.I,
)
_CITATION_IN_PROSE = re.compile(rf"(?<!\w)({_CITATION_LABEL})[\s-]*0*([0-9]{{1,2}})(?!\w)", re.I)
_SEPARATOR = re.compile(r"\s*(?:[,;&]\s*(?:and\b)?|\band\b| और )\s*", re.I)
# Selected lookalikes for the letters used in DPDP, DPDPA and DPDPR.
_CONFUSABLES = str.maketrans("ДдԀԁРрΡρАаΑαᎡꓣ", "DdDdPpPpAaAaRR")


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


def is_pinned_source(url):
    return _url_identity(url) in _SOURCE


def _without_format_characters(text):
    return "".join(char for char in text if category(char) != "Cf")


def _normalized(text):
    folded = normalize("NFKC", _without_format_characters(text)).translate(_CONFUSABLES)
    return "".join(str(decimal(char, char)) for char in folded)


def has_explanation(text):
    words = re.findall(r"[^\W\d_]+", _without_format_characters(text).casefold())
    return len(set(words)) >= 6


def _whole_phases(instrument):
    result = {}
    for phase, provisions in _REGISTRY[instrument]["whole_provisions"].items():
        for provision in provisions:
            start, *end = provision.split("-")
            for number in range(int(start), int(end[0] if end else start) + 1):
                result[number] = phase
    return result


_WHOLE = {instrument: _whole_phases(instrument) for instrument in ("act", "rules")}
_PROVISION_NUMBERS = {
    kind: whole.keys() | {int(number) for number in _REGISTRY[kind]["split_provisions"]}
    for kind, whole in _WHOLE.items()
}


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


def _citation_kind(label):
    return "rules" if label.lower().startswith("r") or label == "नियम" else "act"


def _could_cite_dpdp(provision_text):
    kind = None
    for term in _SEPARATOR.split(provision_text.strip()):
        match = _CITATION.fullmatch(term)
        if not match:
            continue
        label, number, parts, end = match.groups()
        if label:
            kind = _citation_kind(label)
        if kind and not (end and parts):
            numbers = range(int(number), int(end or number) + 1)
            if not _PROVISION_NUMBERS[kind].isdisjoint(numbers):
                return True
    return any(
        int(number) in _PROVISION_NUMBERS[_citation_kind(label)]
        for label, number in _CITATION_IN_PROSE.findall(provision_text)
    )


def _classify(entry):
    instrument = _normalized(entry["instrument"])
    provision_text = _normalized(entry["provision"])
    url_identity = _url_identity(entry.get("source_url", ""))
    source = _SOURCE.get(url_identity)
    source_path = re.sub(r"[-_]", " ", url_identity[1]) if url_identity else ""
    india_context = _INDIA.search(instrument) or _INDIA.search(source_path)
    if _RULES_OF.search(instrument) or (india_context and _RULES_OF_SHORT_ACT.search(instrument)):
        instruments = {"rules"}
    else:
        instruments = {kind for kind, pattern in _INSTRUMENT.items() if pattern.search(instrument)}
        if india_context:
            instruments.update(kind for kind, pattern in _UNDATED_INSTRUMENT.items() if pattern.search(instrument))
    if not instruments and not source:
        if any(_DPDP_HINT.search(text) for text in (source_path, instrument, provision_text)):
            return set(), "unmapped_dpdp"
        if not _OTHER_INSTRUMENT.search(instrument):
            if _is_official_host(url_identity):
                return set(), "unidentified_official"
            if _could_cite_dpdp(provision_text):
                return set(), "unidentified_numbered"
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
            kind = _citation_kind(explicit)
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
    if unmapped == "unidentified_numbered":
        return [f'{entry["id"]}: Citation could refer to a DPDP provision. '
                'Supply the specific instrument title or notification identifier and verify the source.']
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
            if unmapped == "unidentified_numbered":
                return [f"{identifier}: Citation could refer to a DPDP provision. "
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
        notes = entry.get("notes", "")
        if not has_explanation(notes) or not _UNCERTAINTY_REASON.search(_without_format_characters(notes)):
            errors.append(f"{identifier}: uncertainty after the latest DPDP commencement requires "
                          "notes explaining the unresolved source or legal issue.")
    return errors
