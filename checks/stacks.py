"""Conservative, non-exclusive platform hints from supplied evidence."""

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from .evidence import EvidenceBundle, ORIGIN_REF


SHOPIFY_ARTIFACTS = ("shopify.app.toml", "shopify.extension.toml", "shopify-theme.js")
WOOCOMMERCE_ARTIFACTS = ("woocommerce-settings.json", "woocommerce-plugins.json", "woocommerce-plugin.php")
PLATFORMS = ("shopify", "woocommerce")


@dataclass(frozen=True)
class StackDetection:
    stack: str
    signals: tuple[str, ...]
    confidence: str


def detect_stacks(bundle: EvidenceBundle) -> tuple[StackDetection, ...]:
    """Return all supported platform hints, or the generic fallback."""
    signals = {stack: [] for stack in PLATFORMS}
    configs = {"shopify": SHOPIFY_ARTIFACTS, "woocommerce": WOOCOMMERCE_ARTIFACTS}
    for stack, names in configs.items():
        for name in names:
            if name in bundle.artifact_names and bundle.artifact_text(name).strip():
                signals[stack].append(bundle.line_ref(name, 1, len(bundle.artifact_text(name).splitlines())))

    for name in bundle.artifact_names:
        ref = bundle.artifact_ref(name, "platform")
        if bundle.resolves(ref):
            platform = bundle.resolve(ref)
            if platform in PLATFORMS:
                signals[platform].append(ref)

    packet = bundle.packet or {}
    # authorized_origin is the nominated origin, available even when capture fails.
    if _shopify_origin(packet.get("authorized_origin")):
        signals["shopify"].append(ORIGIN_REF)
    observations = packet.get("observations")
    if isinstance(observations, list):
        for index, observation in enumerate(observations):
            requests = observation.get("requests") if isinstance(observation, dict) else None
            if not isinstance(requests, list):
                continue
            for request_index, request in enumerate(requests):
                stack = _request_stack(request)
                if stack:
                    signals[stack].append(bundle.packet_ref(index, "requests", request_index, "path"))

    detected = tuple(StackDetection(stack, tuple(refs), "medium" if len(refs) == 1 else "high")
                     for stack, refs in signals.items() if refs)
    return detected or (StackDetection("generic", (), "low"),)


def _shopify_origin(origin):
    if not isinstance(origin, str):
        return False
    try:
        host = urlsplit(origin).hostname or ""
    except ValueError:
        return False
    return re.fullmatch(r"[a-z0-9-]+\.myshopify\.com", host) is not None


def _request_stack(request):
    if not isinstance(request, dict) or request.get("attempt_evidence_status") != "observed":
        return None
    path = request.get("path")
    if not isinstance(path, str):
        return None
    if path.startswith("/cdn/shop/"):
        return "shopify"
    if path.startswith("/wp-content/plugins/woocommerce/"):
        return "woocommerce"
    return None
