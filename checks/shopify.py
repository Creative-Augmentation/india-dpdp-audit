"""Structural Shopify checks over redacted, supplied evidence.

Supply optional_paths from the packet's approved request paths, a standalone
theme entry script and any assets named in its scripts inventory, and a pixels
inventory with each pixel's purposes and its customer_privacy or TOML config.
The app check uses a subject distribution record before reading the app TOML.
"""

from bisect import bisect_right
import json
import re

from .contract import Basis, Check, CheckResult, Fix, Need, Retest
from .registry import register


PATHS = "optional-request-paths.json"
THEME = "shopify-theme.js"
THEME_INVENTORY = "shopify-theme.json"
PIXELS = "shopify-pixels.json"
CHECKOUT = "shopify-checkout.json"
SUBJECT = "shopify-subject.json"
APP_CONFIG = "shopify.app.toml"

ALLOWED_PATH = re.compile(r"/[A-Za-z0-9/_.~-]{0,199}")
ASSET_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
PURPOSES = {"analytics", "marketing", "preferences"}
OPTIONAL_PURPOSES = {"analytics", "marketing"}
REJECTION_PHASES = ("initial", "reject", "revisit_after_reject")
CHOICE_PHASES = REJECTION_PHASES + ("accept", "revisit_after_accept", "withdraw",
                                  "revisit_after_withdraw")
REQUEST_NEEDS = (Need("artifact", PATHS, "/optional_paths"), *(
    Need("packet", phase, "/requests") for phase in REJECTION_PHASES
))
THEME_NEED = Need("artifact", THEME)
PIXEL_NEED = Need("artifact", PIXELS, "/pixels")
CHECKOUT_NEED = Need("artifact", CHECKOUT, "/marketing_opt_in_default")
APP_NEEDS = (Need("artifact", SUBJECT, "/distribution"), Need("artifact", APP_CONFIG))


def _unverified(observation, missing, request):
    return CheckResult("could_not_check", observation, missing=(missing,), evidence_request=request)


def _read(bundle, ref):
    try:
        return bundle.resolve(ref)
    except LookupError:
        return None


def _optional_requests(bundle):
    path_ref = bundle.artifact_ref(PATHS, "optional_paths")
    paths = bundle.resolve(path_ref)
    if not isinstance(paths, list) or not paths or any(
        not isinstance(path, str) or not ALLOWED_PATH.fullmatch(path)
        or any(segment in (".", "..") for segment in path.split("/")) for path in paths
    ):
        return _unverified("The optional request paths for this capture were unavailable.",
                           "approved paths classified as optional for this capture",
                           "Supply the approved optional paths used by the collector for this packet.")
    paths = set(paths)

    phases = {}
    for index, row in enumerate(bundle.packet["observations"]):
        if not isinstance(row, dict) or row.get("phase") not in REJECTION_PHASES:
            continue
        phase = row["phase"]
        if phase in phases or not isinstance(row.get("requests"), list):
            return _unverified("The rejection branch has ambiguous request records.",
                               "one request list per rejection phase",
                               "Supply a new packet with the initial, rejection and rejection revisit phases.")
        phases[phase] = index, row["requests"]

    reject_index, _ = phases["reject"]
    reject_refs = (path_ref, bundle.packet_ref(reject_index, "status"))
    sampled = []
    for phase in ("initial", "revisit_after_reject"):
        index, requests = phases[phase]
        sampled.append(bundle.packet_ref(index, "requests"))
        for request_index, request in enumerate(requests):
            if (not isinstance(request, dict) or request.get("attempt_evidence_status") != "observed"
                    or "path" not in request
                    or (request["path"] is not None and not isinstance(request["path"], str))):
                return _unverified("A sampled request lacked an observed attempt.",
                                   "complete request-attempt evidence for the rejection branch",
                                   "Recollect the initial and post-rejection request observations.")
            if request["path"] not in paths:
                continue
            timing = "before a choice" if phase == "initial" else "on the revisit after rejection"
            return CheckResult(
                "gap", f"The browser attempted an approved optional request {timing}.",
                (*reject_refs, bundle.packet_ref(index, "requests", request_index)),
                fix=Fix(
                    "Storefront consent gating for the sampled optional requests", "merchant developer",
                    "Read the initial permission state and gate optional requests on a matching choice.",
                    "In staging, optional requests are absent before choice, after rejection and after "
                    "withdrawal, including revisits. Acceptance permits the expected optional request.",
                    Retest(
                        (REQUEST_NEEDS[0], *(Need("packet", name, "/requests") for name in CHOICE_PHASES)),
                        "The new observed rejection branch has no approved optional attempts before choice "
                        "or on revisit. The staged accept and withdraw traces confirm the expected sequence.",
                    ),
                ),
            )
    return CheckResult("ok", "No approved optional request attempts appeared before choice or on the "
                       "revisit after rejection for the sampled path and observation window.",
                       (*reject_refs, *sampled))


register(Check(
    "SHP-01a", "shopify", "Optional requests before consent or after rejection",
    Basis("good_practice", note="Optional processing can be gated on the visitor's choice."),
    REQUEST_NEEDS, _optional_requests,
))


# Review only recognizable static JavaScript. Unknown syntax can hide a send or
# change its control flow, so it prevents an all-clear for the supplied scripts.
_JS_INERT = re.compile(
    r"""(?P<string>"(?:[^"\\\r\n]|\\[^\r\n])*"|'(?:[^'\\\r\n]|\\[^\r\n])*')"""
    r"|(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)"
)
_JS_VALUE = r'"(?:visitorConsentCollected|event|text)"'
_JS_WHITESPACE = re.compile(r"\s*")
_JS_SEND = re.compile(
    rf'(?:(?P<call>(?:window\s*\.\s*)?(?:Shopify\s*\.\s*analytics\s*\.\s*publish'
    rf'|analytics\s*\.\s*track|marketing\s*\.\s*track))\s*\(\s*{_JS_VALUE}'
    rf'|(?P<gtag>gtag)\s*\(\s*"event"\s*,\s*{_JS_VALUE})\s*\)\s*;'
)
_JS_IDENTIFIER = r"[A-Za-z_$][\w$]*"
_JS_PERMISSION = (
    r"(?:window\s*\.\s*)?Shopify\s*\.\s*customerPrivacy\s*\.\s*"
    r"(?P<permission>analyticsProcessingAllowed|marketingAllowed)\s*\(\s*\)"
)
_JS_GUARD = re.compile(
    rf"if\s*\(\s*(?:{_JS_PERMISSION}|(?P<binding>{_JS_IDENTIFIER}))\s*\)\s*"
    r"\{(?P<body>[^{}]*)\}"
)
_JS_LISTENER = re.compile(
    r'document\s*\.\s*addEventListener\s*\(\s*"visitorConsentCollected"\s*,\s*'
    rf"(?:\(\s*\)\s*=>|function\s*\(\s*(?P<argument>{_JS_IDENTIFIER})?\s*\))\s*"
    r"\{(?P<body>[\s\S]*?)\}\s*\)\s*;"
)
_JS_DECLARATION = re.compile(
    rf"const\s+(?P<name>{_JS_IDENTIFIER})\s*=\s*(?:{_JS_PERMISSION}|{_JS_VALUE})\s*;"
)
_JS_SYMBOLS = {"analytics", "marketing", "gtag", "window", "Shopify", "document"}


def _mask_js_token(match):
    if match.lastgroup == "comment":
        return re.sub(r"[^\n]", " ", match[0])
    value = match[0][1:-1]
    return f'"{value}"' if value in ("visitorConsentCollected", "event") else '"text"'


def _theme_events(text):
    """Yield (unguarded, startup, first line, last line) for recognized event sends."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.count("\n") + bool(text and not text.endswith("\n")) != len(text.splitlines()):
        raise ValueError("Unsupported JavaScript line boundaries.")
    script = _JS_INERT.sub(_mask_js_token, text)
    newlines = [match.start() for match in re.finditer("\n", script)]

    def events(start, end, *, startup, permission=None, guard_start=None, guard_end=None):
        bindings = {}
        while (start := _JS_WHITESPACE.match(script, start, end).end()) < end:
            if send := _JS_SEND.match(script, start, end):
                call = send["call"] or send["gtag"]
                purpose = ("marketingAllowed" if re.sub(r"\s+", "", call).endswith("marketing.track")
                           else "analyticsProcessingAllowed")
                guarded = permission == purpose
                first, last = (guard_start, guard_end) if guarded else send.span()
                yield (not guarded, startup, bisect_right(newlines, first) + 1,
                       bisect_right(newlines, last - 1) + 1)
                start = send.end()
            elif permission is None and (gate := _JS_GUARD.match(script, start, end)):
                binding = gate["binding"]
                if binding is None:
                    gate_permission, read_start = gate["permission"], gate.start()
                elif binding in bindings and bindings[binding]["permission"] is not None:
                    read = bindings[binding]
                    gate_permission, read_start = read["permission"], read.start()
                else:
                    raise ValueError("Unsupported guard expression.")
                yield from events(*gate.span("body"), startup=startup, permission=gate_permission,
                                  guard_start=read_start, guard_end=gate.end())
                start = gate.end()
            elif startup and permission is None and (listener := _JS_LISTENER.match(script, start, end)):
                if listener["argument"] in _JS_SYMBOLS:
                    raise ValueError("A recognized JavaScript name was shadowed.")
                yield from events(*listener.span("body"), startup=False)
                start = listener.end()
            elif startup and permission is None and (declaration := _JS_DECLARATION.match(script, start, end)):
                name = declaration["name"]
                if name in _JS_SYMBOLS or name in bindings:
                    raise ValueError("A recognized JavaScript name was redefined.")
                bindings[name] = declaration
                start = declaration.end()
            else:
                raise ValueError("Unsupported JavaScript statement.")

    yield from events(0, len(script), startup=True)


def _theme_consent(bundle):
    scripts = [THEME]
    if THEME_INVENTORY in bundle.artifact_names:
        listed = _read(bundle, bundle.artifact_ref(THEME_INVENTORY, "scripts"))
        if not isinstance(listed, list) or any(
            not isinstance(name, str) or not ASSET_NAME.fullmatch(name) or not name.endswith(".js")
            for name in listed
        ):
            return _unverified("The theme script inventory could not be read.",
                               "names of supplied JavaScript assets",
                               "Supply a script inventory with local JavaScript artifact names.")
        scripts.extend(name for name in dict.fromkeys(listed) if name != THEME)

    if any(name not in bundle.artifact_names or not bundle.artifact_text(name).strip() for name in scripts):
        return _unverified("A referenced theme script was unavailable.",
                           "all referenced theme scripts",
                           "Supply the deployed theme entry script and the source of each referenced asset.")

    unguarded, guarded = [], []
    initialization_guard = False
    try:
        for name in scripts:
            for is_unguarded, startup, first, last in _theme_events(bundle.artifact_text(name)):
                ref = bundle.line_ref(name, first, last)
                if is_unguarded:
                    unguarded.append((ref, startup))
                else:
                    guarded.append(ref)
                    initialization_guard |= startup
    except ValueError:
        return _unverified("The supplied theme source has unreviewed statements or script references.",
                           "reviewable initialization code and referenced source",
                           "Supply a redacted, standalone excerpt containing the full optional-event "
                           "initialization and consent listener, with referenced sources.")

    if unguarded:
        ref, startup = unguarded[0]
        location = "during initialization" if startup else "in a visitorConsentCollected listener"
        return CheckResult(
            "gap", f"The supplied theme code sends an optional event {location} without a guarding "
            "read of the corresponding Shopify privacy state.",
            (ref,),
            fix=Fix(
                "Theme initialization and optional-event consent listener", "merchant developer",
                "Gate optional sends on the current Shopify permission at initialization and on choice changes.",
                "In a fresh staging session, the theme reads the matching permission before sending. "
                "Rejecting or withdrawing leaves the event unsent, including on reload.",
                Retest((THEME_NEED,), "The new theme source shows a matching initialization guard "
                       "and no supported optional sends outside a matching consent guard."),
            ),
        )
    if initialization_guard:
        return CheckResult("ok", "In the supplied theme code, the reviewed optional event sends use "
                           "the matching Shopify privacy permission, including at initialization.",
                           tuple(dict.fromkeys(guarded)))
    return _unverified("No guarded initialization send could be established.",
                       "reviewable optional-event initialization",
                       "Supply the theme initialization code that reads the applicable privacy permission "
                       "and sends the optional event.")


register(Check(
    "SHP-01b", "shopify", "Theme privacy state at initialization",
    Basis("good_practice", note="The current consent state is needed at startup and on choice changes."),
    (THEME_NEED,), _theme_consent,
))


# Python 3.10 has no TOML parser in the standard library. Read the bare-key
# tables, scalars and arrays used by the redacted Shopify config excerpts.
# Reject other syntax instead of treating an unreadable field as absent.
_TOML_STRING = (
    r'"(?:[^"\\\x00-\x1f]|\\(?:["\\bfnrt]|u[0-9a-fA-F]{4}))*"'
    r"|'[^'\x00-\x1f]*'"
)
_TOML_ATOM = rf"{_TOML_STRING}|true|false|[+-]?(?:0|[1-9][0-9]*)"
_TOML_ATOMS = re.compile(_TOML_ATOM)
_TOML_KEY = r"[A-Za-z0-9_-]+"
_TOML_NAME = rf"{_TOML_KEY}(?:[ \t]*\.[ \t]*{_TOML_KEY})*"
_TOML_INERT = re.compile(rf"(?P<string>{_TOML_STRING})|(?P<comment>\#[^\n]*)")
_TOML_LINE = re.compile(
    rf"[ \t]*(?:\[\[(?P<array>{_TOML_NAME})\]\]|\[(?P<table>{_TOML_NAME})\]|"
    rf"(?P<key>{_TOML_KEY})[ \t]*=[ \t]*(?P<value>{_TOML_ATOM}|"
    rf"\[\s*(?:(?:{_TOML_ATOM})(?:\s*,\s*(?:{_TOML_ATOM}))*\s*(?:,\s*)?)?\]))"
    r"[ \t]*(?:\n|\Z)"
)
_TOML_BLANK = re.compile(r"[ \t]*(?:\n|\Z)")


def _toml_atom(value):
    if value.startswith("'"):
        return value[1:-1]
    if value.startswith("+"):
        return int(value)
    return json.loads(value)


def _toml_sections(text):
    """Return (dotted table, is array table, values, first line, last line)."""
    text = text.replace("\r\n", "\n")
    text = _TOML_INERT.sub(lambda match: "" if match.lastgroup == "comment" else match[0], text)
    cursor, line = 0, 1
    sections = []
    name, array, values, first, last = "", False, {}, 1, 1
    headings, children = {}, {}
    while cursor < len(text):
        blank = _TOML_BLANK.match(text, cursor)
        if blank:
            cursor = blank.end()
            line += 1
            continue
        item = _TOML_LINE.match(text, cursor)
        if item is None:
            raise ValueError("Unsupported TOML syntax.")
        span = item[0].count("\n")
        if item["array"] or item["table"]:
            sections.append((name, array, values, first, last))
            name = re.sub(r"[ \t]", "", item["array"] or item["table"])
            array = item["array"] is not None
            if name in headings and not (headings[name] and array):
                raise ValueError("Repeated TOML table.")
            headings[name] = array
            parent = ""
            parts = name.split(".")
            if len(parts) > 16:
                raise ValueError("Unsupported TOML table depth.")
            for part in parts:
                children.setdefault(parent, set()).add(part)
                parent = f"{parent}.{part}" if parent else part
            values, first, last = {}, line, line
        elif key := item["key"]:
            if key in values:
                raise ValueError("Repeated TOML key.")
            raw = item["value"]
            values[key] = ([_toml_atom(atom[0]) for atom in _TOML_ATOMS.finditer(raw)]
                           if raw.startswith("[") else _toml_atom(raw))
            last = line + span - item[0].endswith("\n")
        line += span
        cursor = item.end()
    sections.append((name, array, values, first, last))
    for name, _, values, _, _ in sections:
        if values.keys() & children.get(name, set()):
            raise ValueError("Conflicting TOML key and table.")
    return sections


def _pixel_privacy(bundle, pixel, index, purposes):
    if "config" not in pixel:
        privacy = pixel.get("customer_privacy", {})
        refs = (bundle.artifact_ref(PIXELS, "pixels", index),)
        if isinstance(privacy, dict) and purposes.issubset(privacy):
            refs = tuple(bundle.artifact_ref(PIXELS, "pixels", index, "customer_privacy", purpose)
                         for purpose in sorted(purposes))
        return privacy, refs

    name = pixel["config"]
    if (not isinstance(name, str) or not name.endswith(".toml")
            or name not in bundle.artifact_names or "customer_privacy" in pixel):
        raise ValueError("Missing or ambiguous pixel configuration.")
    text = bundle.artifact_text(name)
    sections = _toml_sections(text)
    root = sections[0][2]
    if root.get("type") != "web_pixel_extension" or "customer_privacy" in root:
        raise ValueError("Expected a web pixel extension with a customer privacy table.")
    privacy = {}
    for section, array, values, _, _ in sections:
        if section == "customer_privacy":
            if array:
                raise ValueError("Expected a single customer privacy table.")
            privacy = values
        elif section.startswith("customer_privacy."):
            raise ValueError("Unsupported nested customer privacy table.")
    return privacy, (bundle.line_ref(name, 1, len(text.splitlines())),)


def _pixels(bundle):
    inventory = bundle.resolve(bundle.artifact_ref(PIXELS, "pixels"))
    refs = []
    try:
        if not isinstance(inventory, list):
            raise ValueError("Expected a pixel inventory.")
        for index, pixel in enumerate(inventory):
            purposes = pixel.get("purposes") if isinstance(pixel, dict) else None
            if not isinstance(purposes, list) or not purposes or any(
                not isinstance(purpose, str) or purpose not in PURPOSES for purpose in purposes
            ):
                raise ValueError("Unknown pixel purposes.")
            optional = OPTIONAL_PURPOSES.intersection(purposes)
            if not optional:
                continue
            privacy, config_refs = _pixel_privacy(bundle, pixel, index, optional)
            if not isinstance(privacy, dict) or any(
                purpose in privacy and type(privacy[purpose]) is not bool for purpose in optional
            ):
                raise ValueError("Expected boolean privacy requirements.")
            pixel_refs = (bundle.artifact_ref(PIXELS, "pixels", index, "purposes"), *config_refs)
            missing = sorted(purpose for purpose in optional if privacy.get(purpose) is not True)
            if missing:
                return CheckResult(
                    "gap", f"A declared pixel lacks explicit customer_privacy requirements for "
                    f"{', '.join(missing)}. The declarations describe configuration only.",
                    pixel_refs,
                    fix=Fix(
                        "Privacy requirements for the listed pixel",
                        "app developer" if "config" in pixel else "merchant developer",
                        "Declare the applicable analytics and marketing requirements in the pixel settings "
                        "or the app extension config.",
                        "The redacted pixel declares each inventoried optional purpose as required, and a "
                        "staging capture shows the pixel gated on those choices.",
                        Retest((PIXEL_NEED,), "The updated inventory and any referenced configuration "
                               "declare the matching privacy requirements for every listed optional pixel."),
                    ),
                )
            refs.extend(pixel_refs)
    except (ValueError, RecursionError):
        return _unverified("A supplied pixel inventory or configuration could not be evaluated.",
                           "readable declarations of pixel purposes and privacy requirements",
                           "Supply the redacted pixel inventory and customer privacy settings or extension config.")
    if not refs:
        return _unverified("The inventory did not identify a pixel with a declared optional purpose.",
                           "an inventoried analytics or marketing pixel",
                           "Supply declarations of purpose and settings for any analytics or marketing pixel.")
    return CheckResult("ok", "The supplied settings explicitly require the declared analytics or "
                       "marketing permissions for the listed optional pixels.", tuple(dict.fromkeys(refs)))


register(Check(
    "SHP-01c", "shopify", "Explicit pixel privacy requirements",
    Basis("good_practice", note="Explicit pixel privacy settings make the required permissions reviewable."),
    (PIXEL_NEED,), _pixels,
))


def _marketing_default(bundle):
    ref = bundle.artifact_ref(CHECKOUT, "marketing_opt_in_default")
    selected = bundle.resolve(ref)
    if type(selected) is not bool:
        return _unverified("The checkout settings did not show a boolean marketing default.",
                           "the explicit marketing opt-in default",
                           "Supply the redacted checkout marketing opt-in default as true or false.")
    if selected:
        return CheckResult(
            "gap", "The supplied checkout settings preselect the marketing opt-in.",
            (ref,),
            fix=Fix(
                "Checkout marketing opt-in default", "merchant operations",
                "Set the opt-in to unselected by default for the sampled checkout configuration.",
                "A fresh staged checkout shows the marketing choice unchecked before any interaction.",
                Retest((CHECKOUT_NEED,), "The updated redacted checkout configuration explicitly shows "
                       "an unselected default."),
            ),
        )
    return CheckResult("ok", "The supplied checkout settings leave the marketing opt-in unselected "
                       "by default.", (ref,))


register(Check(
    "SHP-01d", "shopify", "Checkout marketing opt-in default",
    Basis("good_practice", note="An unselected default leaves the marketing choice to the customer."),
    (CHECKOUT_NEED,), _marketing_default,
))


COMPLIANCE_TOPICS = ("customers/data_request", "customers/redact", "shop/redact")


def _app_webhooks(bundle):
    subject_ref = bundle.artifact_ref(SUBJECT, "distribution")
    if _read(bundle, subject_ref) != "shopify_app_store":
        return _unverified(
            "App Store distribution for the subject could not be established.",
            "subject is an app distributed through the app store, not shown",
            "Supply a redacted App Store listing or distribution record for the assessed app.",
        )
    if not bundle.has_need(APP_NEEDS[1]):
        return _unverified("The applicable app configuration was unavailable.",
                           APP_CONFIG, "Supply the redacted Shopify app configuration used for deployment.")

    text = bundle.artifact_text(APP_CONFIG)
    topics, refs = set(), [subject_ref]
    try:
        sections = _toml_sections(text)
        if "webhooks" in sections[0][2]:
            raise ValueError("Expected a webhooks table.")
        for name, array, values, first, last in sections:
            if name == "webhooks" and (array or "subscriptions" in values):
                raise ValueError("Expected app webhook subscriptions as array tables.")
            if name.startswith("webhooks.subscriptions."):
                raise ValueError("Unsupported nested webhook subscription table.")
            if name != "webhooks.subscriptions":
                continue
            declared = values.get("compliance_topics", [])
            if not array or not isinstance(declared, list) or any(
                not isinstance(topic, str) for topic in declared
            ):
                raise ValueError("Expected a compliance topic list per subscription.")
            uri = values.get("uri")
            if declared and isinstance(uri, str) and uri and not any(char.isspace() for char in uri):
                topics.update(declared)
                refs.append(bundle.line_ref(APP_CONFIG, first, last))
    except (ValueError, RecursionError):
        return _unverified("The app webhook configuration could not be evaluated.",
                           "readable compliance subscription tables",
                           "Supply the redacted app config with its compliance topics and subscription destinations.")

    missing = [topic for topic in COMPLIANCE_TOPICS if topic not in topics]
    if missing:
        return CheckResult(
            "gap", f"The supplied App Store app config is missing compliance subscriptions for "
            f"{', '.join(missing)}. This checks subscription configuration only.",
            (subject_ref, bundle.line_ref(APP_CONFIG, 1, len(text.splitlines()))),
            fix=Fix(
                "App compliance webhook subscriptions", "app developer",
                "Add each missing topic to a compliance subscription and deploy the updated app config.",
                "The redacted deployed app config lists each mandatory compliance topic under "
                "a subscription with a destination.",
                Retest(APP_NEEDS, "The new app configuration declares subscriptions with destinations for "
                       "customers/data_request, customers/redact and shop/redact."),
            ),
        )
    return CheckResult("ok", "The supplied App Store app config declares all three required compliance "
                       "webhook subscriptions. This checks subscription configuration only.", tuple(refs))


# Applicability must be checked before requesting the configuration, including
# when both artifacts are missing. APP_NEEDS records the conditional inputs.
register(Check(
    "SHP-03a", "shopify", "App Store compliance webhook subscriptions",
    Basis("good_practice", note="Shopify requires these compliance subscriptions for App Store apps."),
    (), _app_webhooks,
))
