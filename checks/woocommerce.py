"""Structural WooCommerce checks for redacted local evidence exports.

The JSON shapes are represented in checks/fixtures/woocommerce. Retention
periods are strings such as "18 days". Checkout settings attest whether text
or a policy link is configured and identify the sampled collector phase and
zero-based selector index. Capability lists describe assigned roles.
"""

from dataclasses import dataclass
import re

from .contract import Basis, Check, CheckResult, Fix, Need, Retest
from .registry import register


STACK = "woocommerce"
SETTINGS = "woocommerce-settings.json"
SCHEDULE = "woocommerce-retention-schedule.json"
CLEANUP = "woocommerce-cleanup-sample.json"
PLUGINS = "woocommerce-plugins.json"
PLUGIN_SOURCE = "woocommerce-plugin.php"
ROLES = "woocommerce-roles.json"
APPROVED_ROLES = "woocommerce-approved-roles.json"

NOTICE_SETTINGS = Need("artifact", SETTINGS, "/checkout_notice")
INVENTORY = Need("artifact", PLUGINS, "/plugins")
RETENTION_SETTINGS = Need("artifact", SETTINGS, "/retention")
APPROVED_SCHEDULE = Need("artifact", SCHEDULE, "/periods")
SOURCE = Need("artifact", PLUGIN_SOURCE)
ROLE_ASSIGNMENTS = Need("artifact", ROLES, "/assignments")
ROLE_ALLOWLIST = Need("artifact", APPROVED_ROLES, "/approved_roles")

PHASES = {
    "entry", "initial", "initial_before_accept", "reject", "revisit_after_reject",
    "accept", "revisit_after_accept", "withdraw", "revisit_after_withdraw",
}
RECIPIENT_CATEGORIES = {"payment", "analytics", "shipping", "marketing"}
ADMIN_CAPABILITIES = {
    "manage_options", "manage_network", "manage_network_options",
    "activate_plugins", "install_plugins", "update_plugins", "edit_plugins", "delete_plugins",
    "switch_themes", "install_themes", "edit_themes", "update_themes", "delete_themes",
    "update_core", "create_users", "promote_users", "delete_users", "edit_users",
}
PERIOD = re.compile(r"([1-9][0-9]*)\s*(day|week|month|year)s?", re.IGNORECASE)
CLEANUP_OUTCOMES = ("trash", "anonymization", "deletion")


def _unverified(observation, missing, request):
    return CheckResult("could_not_check", observation, missing=(missing,), evidence_request=request)


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _checkout_notice(bundle):
    settings_ref = bundle.artifact_ref(SETTINGS, "checkout_notice")
    settings = bundle.resolve(settings_ref)
    if not isinstance(settings, dict) or settings.get("configured") is not True:
        return _unverified("A configured checkout notice could not be established.",
                           "Checkout privacy notice configuration",
                           "Supply redacted settings confirming checkout privacy text or a policy link.")
    phase, selector = settings.get("phase"), settings.get("selector_index")
    if not isinstance(phase, str) or phase not in PHASES or type(selector) is not int or selector < 0:
        return _unverified("The settings do not identify a checkout notice sample.",
                           "Checkout phase and notice selector index",
                           "Supply the checkout phase and the index of its configured collector selector.")

    observations = (bundle.packet or {}).get("observations")
    phases = [(index, row) for index, row in enumerate(observations) if
              isinstance(row, dict) and row.get("phase") == phase] if isinstance(observations, list) else []
    if len(phases) == 1:
        phase_index, observation = phases[0]
        notices = observation.get("notices")
        if observation.get("status") == "observed" and isinstance(notices, list):
            matches = [(index, notice) for index, notice in enumerate(notices) if
                       isinstance(notice, dict) and type(notice.get("index")) is int and notice["index"] == selector]
            if len(matches) == 1:
                notice_index, notice = matches[0]
                if (type(notice.get("visible_count")) is int and notice["visible_count"] >= 0
                        and notice.get("truncated") is False):
                    notice_ref = bundle.packet_ref(phase_index, "notices", notice_index)
                    if bundle.supports(notice_ref):
                        return _notice_result(settings_ref, notice_ref, notice["visible_count"], phase)
    return _unverified("The selected checkout phase did not provide a complete notice count.",
                       "Observed checkout phase with an untruncated selector count",
                       "Recollect the checkout phase with its notice selector and supply the observed packet.")


def _notice_result(settings_ref, notice_ref, count, phase):
    if count:
        return CheckResult("ok", "The configured selector matched a visible element in the sampled checkout phase. "
                           "The count establishes element presence only.", (settings_ref, notice_ref))
    fix = Fix(
        "Checkout theme or extension rendering the configured privacy notice", "store developer",
        "Render the notice at checkout and update the collector selector if the markup changes.",
        "A fresh observed synthetic checkout phase records at least one visible match for the notice selector.",
        Retest((NOTICE_SETTINGS, Need("packet", phase, "/notices")),
               "The selected checkout selector has a visible match in a fresh complete observation."),
    )
    return CheckResult("gap", "A notice is configured for checkout. Its selector had zero visible matches "
                       "in the sampled checkout phase.", (settings_ref, notice_ref + "/visible_count"), fix=fix)


def _recipient_mapping(bundle):
    ref = bundle.artifact_ref(PLUGINS, "plugins")
    plugins = bundle.resolve(ref)
    if not isinstance(plugins, list) or any(
        not isinstance(plugin, dict) or not _nonblank(plugin.get("extension"))
        or not _nonblank(plugin.get("category")) for plugin in plugins
    ):
        return _unverified("The supplied plugin inventory could not be classified.",
                           "Plugin inventory with an extension label and category for each row",
                           "Supply a redacted inventory with each extension labeled and categorized.")
    unmapped = [
        bundle.artifact_ref(PLUGINS, "plugins", index) for index, plugin in enumerate(plugins)
        if plugin["category"].strip().lower() in RECIPIENT_CATEGORIES
        and not (_nonblank(plugin.get("recipient")) and _nonblank(plugin.get("contract_owner")))
    ]
    if not unmapped:
        return CheckResult("ok", "The supplied inventory records a recipient and contract owner for every listed "
                           "payment, analytics, shipping, or marketing extension. The mapping describes the inventory.",
                           (ref,))
    fix = Fix(
        "Recipient and contract-owner fields in the plugin inventory", "privacy operations",
        "Obtain redacted recipient and contract-owner records and reconcile the missing inventory entries.",
        "Each listed payment, analytics, shipping, or marketing extension has both fields populated.",
        Retest((INVENTORY,), "A fresh redacted export maps every listed extension in the four recipient categories."),
    )
    return CheckResult("gap", "The inventory lists an extension with a missing recipient or contract owner. "
                       "Request the mapping records. The extension listing is a lead for examining transfers.",
                       tuple(unmapped), fix=fix)


def _period(value):
    match = PERIOD.fullmatch(value.strip()) if _nonblank(value) else None
    return (match[1], match[2].lower()) if match else None


def _retention_periods(bundle):
    settings_ref = bundle.artifact_ref(SETTINGS, "retention")
    schedule_ref = bundle.artifact_ref(SCHEDULE, "periods")
    settings, approved = bundle.resolve(settings_ref), bundle.resolve(schedule_ref)
    if not isinstance(settings, dict) or not isinstance(approved, dict) or not approved:
        return _missing_periods()
    blank_refs, different_refs = [], []
    incomplete = False
    for option, scheduled in sorted(approved.items()):
        expected = _period(scheduled)
        if not expected or option not in settings:
            incomplete = True
            continue
        refs = (bundle.artifact_ref(SETTINGS, "retention", option), bundle.artifact_ref(SCHEDULE, "periods", option))
        actual = settings[option]
        if actual is None or isinstance(actual, str) and not actual.strip():
            blank_refs.extend(refs)
        elif (configured := _period(actual)) is None:
            incomplete = True
        elif configured != expected:
            different_refs.extend(refs)
    cleanup_ref = bundle.artifact_ref(CLEANUP, "outcomes")
    sample = bundle.resolve(cleanup_ref) if bundle.resolves(cleanup_ref) else None
    sample_refs = (cleanup_ref,) if isinstance(sample, list) and sample and all(
        item in CLEANUP_OUTCOMES for item in sample
    ) else ()
    limit = " This compares settings. Trash, anonymization and deletion are distinct cleanup outcomes."
    if blank_refs or different_refs:
        observation = []
        if blank_refs:
            observation.append("A scheduled option has a blank setting, which allows indefinite retention for that option.")
        if different_refs:
            observation.append("A configured period differs from the approved schedule.")
        fix = Fix(
            "WooCommerce Accounts & Privacy retention settings", "privacy operations",
            "Set each affected retention period to the period in the approved schedule.",
            "The redacted settings export records the scheduled period for each approved option.",
            Retest((RETENTION_SETTINGS, APPROVED_SCHEDULE),
                   "New settings match each approved period. Verify cleanup outcomes separately."),
        )
        return CheckResult("gap", " ".join(observation) + limit, tuple(blank_refs + different_refs) + sample_refs, fix=fix)
    if incomplete:
        return _missing_periods()
    return CheckResult("ok", "Configured retention periods match the approved schedule." + limit,
                       (settings_ref, schedule_ref) + sample_refs)


def _missing_periods():
    return _unverified("The retention settings could not be compared with a complete approved schedule.",
                       "Retention settings and corresponding approved periods",
                       "Supply the redacted Accounts & Privacy retention settings and the approved schedule by option.")


def _admin_roles(bundle):
    roles_ref = bundle.artifact_ref(ROLES, "assignments")
    approved_ref = bundle.artifact_ref(APPROVED_ROLES, "approved_roles")
    roles, approved = bundle.resolve(roles_ref), bundle.resolve(approved_ref)
    if not isinstance(roles, list) or not isinstance(approved, list) or not all(map(_nonblank, approved)) or any(
        not isinstance(row, dict) or not _nonblank(row.get("role"))
        or not isinstance(row.get("capabilities"), list) or not all(map(_nonblank, row["capabilities"]))
        for row in roles
    ):
        return _unverified("The role assignments could not be compared with documented approvals.",
                           "Assigned roles with capability lists and an approved-role list",
                           "Supply a redacted assignment export with capabilities and the approved administrator roles.")
    allowed = {role.strip() for role in approved}
    excess = [
        bundle.artifact_ref(ROLES, "assignments", index) for index, row in enumerate(roles)
        if row["role"].strip() not in allowed and ADMIN_CAPABILITIES.intersection(
            capability.strip() for capability in row["capabilities"]
        )
    ]
    if not excess:
        return CheckResult("ok", "The supplied export shows administrator-level capabilities used by assigned roles "
                           "within the approved list.", (roles_ref, approved_ref))
    fix = Fix(
        "Assigned WordPress roles with administrator-level capabilities", "store security",
        "Reconcile the affected assignments with the approved access list and remove unapproved elevation.",
        "A redacted assignment export contains no unapproved role with administrator-level capabilities.",
        Retest((ROLE_ASSIGNMENTS, ROLE_ALLOWLIST),
               "A fresh export shows all assigned roles with administrator-level capabilities within the approved list."),
    )
    return CheckResult("gap", "The role export shows an assignment with administrator-level capabilities outside "
                       "the supplied approved-role list.", (*excess, approved_ref), fix=fix)


PHP_OPEN = re.compile(r"<\?php(?=\s|$)|<\?=", re.IGNORECASE)
PHP_TOKEN = re.compile(
    r"\s+|/\*[\s\S]*?\*/|(?://|#(?!\[))(?:(?!\?>)[^\n])*"
    r"|\$\w+|\\?\w+(?:\\\w+)*|\?->|->|::|=>|."
)
HEREDOC = re.compile(r"""<<<[ \t]*(?P<quote>['"]?)(?P<label>[A-Za-z_]\w*)(?P=quote)[ \t]*\n""")
PERSONAL_FIELD = re.compile(
    r"(?:^|[_-])(?:email(?:_address)?|phone(?:_number)?|mobile|contact_number|"
    r"first_name|last_name|full_name|contact_name|recipient_name|street_address|"
    r"(?:billing|shipping|delivery)_address(?:_[12])?|date_of_birth|birth_date)$",
    re.IGNORECASE,
)
ERASER_FILTER = "wp_privacy_personal_data_erasers"
USER_META_WRITES = {"add_user_meta", "update_user_meta"}
ORDER_META_WRITES = {"add_meta_data", "update_meta_data"}
TABLE_WRITES = {"insert", "update", "replace"}
DELIMITERS = {"(": ")", "[": "]", "{": "}"}


@dataclass(frozen=True)
class _Token:
    text: str
    first_line: int
    last_line: int


def _quoted_end(source, start):
    quote = source[start]
    cursor = start + 1
    while cursor < len(source):
        char = source[cursor]
        if char == quote:
            return cursor + 1
        if char == "\\":
            cursor += 2
            continue
        if quote != "'" and (source.startswith("{$", cursor) or source.startswith("${", cursor)):
            depth = 1
            cursor += 2
            while depth and cursor < len(source):
                char = source[cursor]
                if char in "'\"" or char == chr(96):
                    cursor = _quoted_end(source, cursor)
                    continue
                depth += (char == "{") - (char == "}")
                cursor += 1
            continue
        cursor += 1
    raise ValueError("Incomplete PHP literal")


def _php_tokens(source):
    """Read PHP tokens without evaluating source. Ignore non-code regions."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    tokens, cursor, line = [], 0, 1
    opened = False
    while cursor < len(source):
        if not opened:
            opening = PHP_OPEN.search(source, cursor)
            if opening is None:
                break
            line += source.count("\n", cursor, opening.end())
            cursor, opened = opening.end(), True
            continue
        if source.startswith("?>", cursor):
            opened = False
            cursor += 2
            continue
        char = source[cursor]
        if char in "'\"" or char == chr(96):
            end = _quoted_end(source, cursor)
            token = source[cursor:end]
        elif source.startswith("<<<", cursor):
            header = HEREDOC.match(source, cursor)
            if not header:
                raise ValueError("Incomplete PHP multiline literal")
            closing = re.compile(r"^[ \t]*" + header["label"] + r"\b", re.MULTILINE).search(source, header.end())
            if not closing:
                raise ValueError("Incomplete PHP multiline literal")
            end, token = closing.end(), "<multiline literal>"
        else:
            matched = PHP_TOKEN.match(source, cursor)
            end, token = matched.end(), matched[0]
            if token == "/" and source.startswith("/*", cursor):
                raise ValueError("Incomplete PHP comment")
        next_line = line + source.count("\n", cursor, end)
        if not token.isspace() and not (token.startswith(("//", "/*", "#")) and token != "#"):
            tokens.append(_Token(token, line, next_line))
        cursor, line = end, next_line
    return tokens


def _closing_tokens(tokens):
    openings, closings = [], {}
    for index, token in enumerate(tokens):
        if token.text in DELIMITERS:
            openings.append(index)
        elif token.text in DELIMITERS.values():
            if not openings or DELIMITERS[tokens[openings[-1]].text] != token.text:
                raise ValueError("Unbalanced PHP delimiters")
            closings[openings.pop()] = index
    if openings:
        raise ValueError("Unbalanced PHP delimiters")
    return closings


def _arguments(tokens, closings, start, end):
    """Return the token ranges of the top-level arguments or array entries."""
    ranges, first = [], start
    while start < end:
        if tokens[start].text == ",":
            ranges.append((first, start))
            first = start + 1
        start = closings.get(start, start) + 1
    if first < end:
        ranges.append((first, end))
    return ranges


def _literal(tokens, bounds):
    start, end = bounds
    value = tokens[start].text if end - start == 1 else ""
    if len(value) >= 2 and value[0] in "'\"" and value[0] == value[-1]:
        return value[1:-1]
    return None


def _personal_field(tokens, bounds):
    value = _literal(tokens, bounds)
    return value is not None and PERSONAL_FIELD.search(value) is not None


def _plain_call(tokens, index):
    before = tokens[index - 1].text.lower() if index else ""
    return before not in {"->", "?->", "::", "function", "new", "&"}


def _custom_table_write(tokens, closings, arguments):
    if len(arguments) < 2:
        return False
    target_start, target_end = arguments[0]
    qualified = target_end - target_start == 5 and [
        item.text for item in tokens[target_start:target_end - 1]
    ] == ["$wpdb", "->", "prefix", "."]
    table = _literal(tokens, (target_end - 1, target_end) if qualified else arguments[0])
    if not table or not re.fullmatch(r"[A-Za-z_]\w*", table):
        return False
    start, end = arguments[1]
    if start < end and tokens[start].text.lower() == "array":
        start += 1
    if closings.get(start) != end - 1:
        return False
    return any(
        end - start >= 3 and tokens[start + 1].text == "=>" and _personal_field(tokens, (start, start + 1))
        for start, end in _arguments(tokens, closings, start + 1, end - 1)
    )


def _callback_argument(tokens, bounds):
    start, end = bounds
    literal = _literal(tokens, bounds)
    return bool(literal and literal.strip()) or start < end and (
        tokens[start].text.startswith("$") or tokens[start].text.lower() in {"[", "array", "function", "fn", "static"}
    )


def _plugin_calls(tokens, closings):
    """Find direct registration and recognizable writes, with source spans."""
    write = None
    ambiguous_hook = False
    order_vars, order_writes = {}, {}
    for index, token in enumerate(tokens[:-1]):
        opening = index + 1
        if tokens[opening].text != "(":
            continue
        name = token.text.removeprefix("\\").lower()
        plain = _plain_call(tokens, index)
        end = closings[opening]
        span = (token.first_line, tokens[end].last_line)
        if plain and name in {"add_filter", "add_action", "call_user_func", "call_user_func_array"}:
            args = _arguments(tokens, closings, opening + 1, end)
            hook = _literal(tokens, args[0]) if args else None
            if name in {"call_user_func", "call_user_func_array"}:
                ambiguous_hook |= hook in {"add_filter", "add_action", "\\add_filter", "\\add_action"}
            elif hook == ERASER_FILTER and len(args) >= 2 and _callback_argument(tokens, args[1]):
                return span, write, ambiguous_hook
            else:
                ambiguous_hook |= hook is None or hook == ERASER_FILTER or "\\" in hook or "$" in hook
        elif plain and name in USER_META_WRITES:
            args = _arguments(tokens, closings, opening + 1, end)
            if len(args) >= 3 and _personal_field(tokens, args[1]):
                write = write or span
        elif plain and name == "wc_get_order" and index >= 2 and tokens[index - 1].text == "=":
            receiver = tokens[index - 2].text
            if receiver.startswith("$"):
                order_vars[receiver] = span[0]
                order_writes.pop(receiver, None)
        elif index >= 2 and tokens[index - 1].text == "->":
            receiver = tokens[index - 2].text
            if receiver == "$wpdb" and name in TABLE_WRITES:
                args = _arguments(tokens, closings, opening + 1, end)
                if _custom_table_write(tokens, closings, args):
                    write = write or (tokens[index - 2].first_line, span[1])
            elif receiver in order_vars and name in ORDER_META_WRITES:
                args = _arguments(tokens, closings, opening + 1, end)
                if len(args) >= 2 and _personal_field(tokens, args[0]):
                    order_writes[receiver] = order_vars[receiver]
            elif receiver in order_writes and name == "save":
                write = write or (order_writes[receiver], span[1])
    return None, write, ambiguous_hook


def _plugin_eraser(bundle):
    source = bundle.artifact_text(PLUGIN_SOURCE)
    try:
        tokens = _php_tokens(source)
        registration, write, ambiguous_hook = _plugin_calls(tokens, _closing_tokens(tokens))
    except (ValueError, RecursionError):
        return _unverified("The supplied PHP could not be inspected completely.",
                           "Complete custom plugin PHP source",
                           "Supply the complete redacted source containing the write and hook registration paths.")
    if registration:
        return CheckResult("ok", "The supplied source contains a direct personal-data erasers filter registration. "
                           "Coverage of external records or backups requires separate verification.",
                           (bundle.line_ref(PLUGIN_SOURCE, *registration),))
    if ambiguous_hook or not write:
        return _unverified("The supplied source did not establish both a personal-data write and its eraser-hook status.",
                           "Recognizable personal-data write and identifiable eraser-hook registrations",
                           "Supply redacted source showing the write and the code that determines the eraser hook name.")
    fix = Fix(
        "Personal-data eraser filter in the custom plugin", "plugin developer",
        "Register a WordPress personal-data eraser for the plugin and implement or document coverage of each store.",
        "The updated source registers the filter and a synthetic staging erasure records an outcome for each mapped store.",
        Retest((SOURCE,), "The new source shows the registration. Separately exercise a synthetic staging erasure "
                          "and verify the outcome or documented exception for each mapped store."),
    )
    return CheckResult("gap", "The supplied plugin source shows a personal-data write and contains no direct "
                       "registration for the personal-data erasers filter.",
                       (bundle.line_ref(PLUGIN_SOURCE, *write),), fix=fix)


for check_id, title, basis, needs, evaluate in (
    ("WOO-01a", "Checkout privacy notice rendering",
     "Compare configured checkout notices with observed rendering.",
     (NOTICE_SETTINGS,), _checkout_notice),
    ("WOO-02a", "Plugin recipient and contract ownership",
     "Maintain traceable recipient and agreement ownership records for extensions.",
     (INVENTORY,), _recipient_mapping),
    ("WOO-03a", "Personal data retention settings",
     "Reconcile configured retention settings with the approved schedule.",
     (RETENTION_SETTINGS, APPROVED_SCHEDULE), _retention_periods),
    ("WOO-03b", "Custom plugin personal-data eraser registration",
     "Register personal-data erasers for custom plugin stores.",
     (SOURCE,), _plugin_eraser),
    ("WOO-04a", "Administrator-level role assignments",
     "Limit elevated capabilities to roles approved for administrative access.",
     (ROLE_ASSIGNMENTS, ROLE_ALLOWLIST), _admin_roles),
):
    register(Check(check_id, STACK, title, Basis("good_practice", note=basis), needs, evaluate))
