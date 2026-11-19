"""Bounded anonymous Chromium observations for owner-authorized pages."""

import asyncio
from collections.abc import Iterable, Mapping
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
from urllib.parse import urlsplit

from .transport import PinnedProxy


ACTIONS = ('accept', 'reject', 'withdraw')
NAVIGATION_MS = 6500
REQUEST_MS = 4000
MAX_REQUESTS = 120
NAT64_PREFIX = ipaddress.IPv6Network('64:ff9b::/96')
PAGE_RESOURCE_GAPS = {'request_limit', 'websocket_blocked', 'unplanned_navigation',
                      'resource_response_unavailable', 'page_resources_incomplete'}
METHOD_OVERRIDE_HEADERS = (
    'x-http-method-override', 'x-http-method', 'x-method-override',
    'http-method-override', 'x-override-method',
)
SAFE_PATH = re.compile(r'/[A-Za-z0-9/_.~-]{0,199}\Z')
HOST_LABEL = re.compile(r'[A-Za-z0-9-]{1,63}\Z')
BROWSER_ARGS = [
    '--proxy-server=http://127.0.0.1:9',
    '--proxy-bypass-list=<-loopback>',
    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
    '--disable-quic',
]


def _origin(url):
    if not isinstance(url, str) or len(url) > 2048 or any(
        ord(char) < 33 or ord(char) == 127 or char == '\\' for char in url
    ):
        raise ValueError('invalid HTTP(S) URL')
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as error:
        raise ValueError('invalid HTTP(S) URL') from error
    if (parts.scheme not in ('https', 'http') or not host
            or parts.username is not None or port == 0):
        raise ValueError('invalid HTTP(S) URL')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('authorize a domain name; IP-literal targets are not supported')
    labels = host.split('.')
    if len(host) > 253 or len(labels) < 2 or labels[-1].isdigit() or labels[-1].startswith('0x') or any(
        not HOST_LABEL.fullmatch(label) or label.startswith('-') or label.endswith('-')
        for label in labels
    ):
        raise ValueError('invalid HTTP(S) host')
    authority = host
    if port is not None and port != (443 if parts.scheme == 'https' else 80):
        authority += f':{port}'
    return f'{parts.scheme}://{authority}'


def _approved_url(url, origin):
    if _origin(url) != origin:
        raise ValueError('page URL must use the authorized origin')
    parts = urlsplit(url)
    if parts.query or parts.fragment or not SAFE_PATH.fullmatch(parts.path or '/'):
        raise ValueError('page URLs require a plain path without query or fragment')
    if url != origin + parts.path or any(segment in ('.', '..') for segment in parts.path.split('/')):
        raise ValueError('page URLs must be canonical')
    return origin + (parts.path or '/')


def _is_public_address(address):
    if address in NAT64_PREFIX:
        address = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return address.is_global and not address.is_multicast


def _require_https(origin):
    if urlsplit(origin).scheme != 'https':
        raise ValueError('public sites require HTTPS')


async def _public_addresses(origin):
    host = urlsplit(origin).hostname
    loop = asyncio.get_running_loop()
    answers = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), 3)
    addresses = tuple(dict.fromkeys(ipaddress.ip_address(item[4][0]) for item in answers))
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise OSError('non-public resolution')
    return tuple(str(address) for address in addresses)


def _strings(values, label, *, limit, width):
    if isinstance(values, str):
        raise ValueError(f'{label} must be a collection of strings')
    values = tuple(values)
    if len(values) > limit or any(not isinstance(value, str) or not value or len(value) > width for value in values):
        raise ValueError(f'invalid {label}')
    return values


def _now():
    return datetime.now(timezone.utc).isoformat()


def _collector_revision():
    root = Path(__file__).resolve().parents[1]
    if not (root / '.git').exists():
        return None
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', 'HEAD'], cwd=root, capture_output=True,
            text=True, check=True, timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _observation(phase):
    return dict(phase=phase, status='not_attempted', reasons=[], page_status=None,
                document_evidence_status='unknown', requests=[], forms=[], notices=[],
                storage={'cookies': None, 'local': None, 'session': None})


SNAPSHOT = r"""(selectors) => {
    const limit = 30;
    const limited = (list) => Array.prototype.slice.call(list, 0, limit);
    const visible = (node) => {
        const style = getComputedStyle(node);
        return node.getClientRects().length > 0 && !['hidden', 'collapse'].includes(style.visibility);
    };
    const forms = document.querySelectorAll('form');
    const controls = (form) => Array.from(form.elements).filter((field) =>
        ['INPUT', 'TEXTAREA', 'SELECT'].includes(field.tagName) && visible(field));
    const storageCount = (name) => {
        try { return window[name].length; } catch { return null; }
    };
    const describedBy = (node) => (node.getAttribute('aria-describedby') || '')
        .split(/\s+/).some((id) => document.getElementById(id) && visible(document.getElementById(id)));
    const missingLabel = (field) => {
        const textEntry = field.tagName === 'TEXTAREA' ||
            (field.tagName === 'INPUT' && ['text', 'search', 'email', 'tel', 'url', 'password'].includes(field.type));
        return textEntry && !field.labels?.length &&
            !['aria-label', 'aria-labelledby', 'title', 'placeholder'].some((attribute) =>
                field.getAttribute(attribute)?.trim());
    };
    const formNodes = limited(forms);
    return {
        empty: !(document.body?.childElementCount || document.body?.textContent.trim()),
        forms: formNodes.map((form) => ({
            visible: visible(form),
            described_by_visible_element: describedBy(form),
            fields: limited(controls(form)).map((field) => ({
                tag: field.tagName.toLowerCase(),
                type: field.type,
                required: field.required,
                labeled: Array.from(field.labels || []).some(visible) || Boolean(field.getAttribute('aria-label')),
                missing_label: missingLabel(field),
                described_by_visible_element: describedBy(field),
            })),
        })),
        notices: selectors.map((selector, index) => {
            try {
                const nodes = document.querySelectorAll(selector);
                return {index, visible_count: limited(nodes).filter(visible).length, truncated: nodes.length > limit};
            } catch { return {index, visible_count: null, truncated: false}; }
        }),
        truncated: forms.length > limit || formNodes.some((form) => controls(form).length > limit),
        storage: {local: storageCount('localStorage'), session: storageCount('sessionStorage')},
    };
}"""


CLICK = r"""(button) => {
    if (!(button instanceof HTMLButtonElement) || button.matches(':disabled') ||
        (button.form && button.type !== 'button')) return false;
    button.click();
    return true;
}"""


class _Journey:
    def __init__(self, origin, paths, selectors, settle_ms, errors):
        self.origin = origin
        self.paths = paths
        self.selectors = selectors
        self.settle_ms = settle_ms
        self.errors = errors
        self.request_count = 0
        self.current = None
        self.page = None
        self.navigation = None
        self.transport = None

    async def route(self, route):
        request = route.request
        observation = self.current
        self.request_count += 1
        if observation is None or self.request_count > MAX_REQUESTS:
            if observation is not None and 'request_limit' not in observation['reasons']:
                observation['reasons'].append('request_limit')
            await route.abort()
            return
        try:
            origin = _origin(request.url)
            path = urlsplit(request.url).path
        except ValueError:
            origin, path = None, None
        method = request.method if request.method in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS') else 'OTHER'
        record = dict(origin=origin if origin == self.origin else None,
                      path=path if origin == self.origin and path in self.paths else None,
                      method=method, resource_type=request.resource_type,
                      attempt_evidence_status='observed', response_evidence_status='unknown',
                      disposition='blocked', status=None, reason=None)
        observation['requests'].append(record)
        if origin != self.origin:
            record['reason'] = 'out_of_scope_origin'
        elif method not in ('GET', 'HEAD'):
            record['reason'] = 'request_method'
        elif request.is_navigation_request() and not self.is_allowed_navigation(request):
            record['reason'] = 'unplanned_navigation'
        if record['reason']:
            await route.abort()
            return
        try:
            await self.forward(route, record, observation)
        except self.errors:
            if self.current is observation:
                record['disposition'] = 'failed'
                record['reason'] = 'request_failed'
            try:
                await route.abort()
            except self.errors:
                pass

    def is_allowed_navigation(self, request):
        try:
            return request.url == self.navigation and request.frame == self.page.main_frame
        except self.errors:
            return False

    async def forward(self, route, record, observation):
        # Fetch one hop. Suppress redirect responses before Chromium can follow them.
        headers = await route.request.all_headers()
        for name in METHOD_OVERRIDE_HEADERS:
            headers.pop(name, None)
        headers['cookie'] = headers.get('cookie', '')
        headers['accept-encoding'] = 'identity'
        response = await self.transport.fetch(route.request.url, method=route.request.method,
                                              headers=headers, max_redirects=0, max_retries=0,
                                              timeout=REQUEST_MS)
        try:
            if self.current is not observation:
                await route.abort()
                return
            record['status'] = response.status
            record['response_evidence_status'] = 'observed'
            if 300 <= response.status < 400 and 'location' in response.headers:
                record['reason'] = 'redirect_suppressed'
                await route.abort()
            else:
                await route.fulfill(response=response)
                if self.current is observation:
                    record['disposition'] = 'observed'
        finally:
            await response.dispose()

    async def block_socket(self, socket_route):
        if self.current is not None and 'websocket_blocked' not in self.current['reasons']:
            self.current['reasons'].append('websocket_blocked')
        await socket_route.close()

    async def snapshot(self, result):
        document = await asyncio.wait_for(self.read_document(), 2)
        if document['empty']:
            result['reasons'].append('empty_document')
        else:
            result['document_evidence_status'] = 'observed'
        result['forms'] = document['forms']
        result['notices'] = document['notices']
        result['storage'].update(document['storage'])
        result['storage']['cookies'] = len(await self.page.context.cookies(self.origin))
        if any(value is None for value in result['storage'].values()):
            result['reasons'].append('storage_unavailable')
        if document['truncated'] or any(notice['truncated'] for notice in result['notices']):
            result['reasons'].append('document_limit')
        if any(notice['visible_count'] is None for notice in result['notices']):
            result['reasons'].append('invalid_notice_selector')

    async def read_document(self):
        # Isolated world prototypes keep page scripts from overriding captured DOM accessors.
        cdp = await self.page.context.new_cdp_session(self.page)
        try:
            frames = await cdp.send('Page.getFrameTree')
            world = await cdp.send('Page.createIsolatedWorld', {
                'frameId': frames['frameTree']['frame']['id'], 'worldName': 'dpdp-collector',
            })
            result = await cdp.send('Runtime.evaluate', {
                'expression': f'({SNAPSHOT})({json.dumps(self.selectors)})',
                'contextId': world['executionContextId'],
                'returnByValue': True,
            })
            if 'exceptionDetails' in result:
                raise TimeoutError('document snapshot unavailable')
            return result['result']['value']
        finally:
            await cdp.detach()

    async def observe(self, result, *, url=None, selector=None):
        self.current = result
        self.navigation = url
        result['status'] = 'blocked'
        try:
            if url:
                response = await self.page.goto(url, wait_until='domcontentloaded', timeout=NAVIGATION_MS)
                result['page_status'] = response.status if response else None
                if response is None or response.status >= 400:
                    result['reasons'].append('document_unavailable')
                    return
            else:
                candidate = self.page.locator(selector)
                if await candidate.count() != 1 or not await candidate.is_visible():
                    result['reasons'].append('action_selector_unavailable')
                    return
                if not await candidate.evaluate(CLICK, timeout=2000):
                    result['reasons'].append('action_requires_visible_non_submit_button')
                    return
            await asyncio.sleep(self.settle_ms / 1000)
            await self.snapshot(result)
            result['status'] = 'observed'
        except self.errors + (TimeoutError, asyncio.TimeoutError):
            result['reasons'].append('navigation_or_observation_failed' if url else 'action_or_observation_failed')
        finally:
            if result['page_status'] is None and url:
                for event in result['requests']:
                    if event['resource_type'] == 'document':
                        result['page_status'] = event['status']
                        break
            self.finish_observation()

    def finish_observation(self):
        result = self.current
        # Requests still pending at the sampling boundary cannot be assigned an outcome.
        for event in result['requests']:
            if event['disposition'] == 'blocked' and event['reason'] is None:
                event['disposition'] = 'pending'
        if any(event['resource_type'] != 'document' and (event['status'] or 0) >= 400
               for event in result['requests']):
            result['reasons'].append('resource_response_unavailable')
        incomplete = dict.fromkeys(event['reason'] or 'request_pending' for event in result['requests']
                                   if event['disposition'] != 'observed')
        result['reasons'].extend(reason for reason in incomplete if reason not in result['reasons'])
        if result['status'] == 'observed' and result['reasons']:
            result['status'] = 'partial'
        self.current = None
        self.navigation = None


async def _collect(packet, url, consent_url, actions, paths, selectors):
    from playwright.async_api import Error, async_playwright

    try:
        playwright_version = version('playwright')
    except PackageNotFoundError:
        playwright_version = None

    origin = packet['authorized_origin']
    observations = {result['phase']: result for result in packet['observations']}
    try:
        addresses = await _public_addresses(origin)
    except (OSError, asyncio.TimeoutError):
        for result in observations.values():
            result['reasons'].append('public_dns_check_failed')
        return

    journey = _Journey(origin, paths, selectors, packet['settle_ms'], (Error,))
    try:
        async with AsyncExitStack() as stack:
            playwright = await stack.enter_async_context(async_playwright())
            parts = urlsplit(origin)
            port = parts.port or (443 if parts.scheme == 'https' else 80)
            proxy = await stack.enter_async_context(PinnedProxy(f'{parts.hostname}:{port}', addresses, port))
            journey.transport = await playwright.request.new_context(proxy={'server': proxy})
            stack.push_async_callback(journey.transport.dispose)
            browser = await playwright.chromium.launch(args=BROWSER_ARGS, chromium_sandbox=True, timeout=8000)
            packet['browser'] = dict(engine='chromium', version=browser.version,
                                     playwright_version=playwright_version)
            try:
                if url != consent_url:
                    await _branch(browser, journey, observations, url, 'entry', (), actions)
                reject = ('reject',) if 'reject' in actions else ()
                await _branch(browser, journey, observations, consent_url, 'initial', reject, actions)
                if 'accept' in actions:
                    sequence = ('accept', 'withdraw') if 'withdraw' in actions else ('accept',)
                    await _branch(browser, journey, observations, consent_url, 'initial_before_accept', sequence, actions)
            finally:
                await browser.close()
    except Error:
        for result in observations.values():
            if result['status'] == 'not_attempted' and not result['reasons']:
                result['reasons'].append('browser_unavailable')


async def _branch(browser, journey, observations, url, first_phase, actions, selectors):
    context = await browser.new_context(service_workers='block', accept_downloads=False)
    try:
        await context.route('**/*', journey.route)
        await context.route_web_socket('**/*', journey.block_socket)
        journey.page = await context.new_page()
        await journey.observe(observations[first_phase], url=url)
        previous = observations[first_phase]
        for action in actions:
            result = observations[action]
            revisit = observations[f'revisit_after_{action}']
            if (PAGE_RESOURCE_GAPS.intersection(previous['reasons'])
                    or any(event['disposition'] != 'observed' for event in previous['requests'])):
                # A quiet click or reload cannot recover the missing evidence from its starting page.
                result['reasons'].append('page_resources_incomplete')
                revisit['reasons'].append('page_resources_incomplete')
            if previous['status'] not in ('observed', 'partial'):
                result['reasons'].append('prior_phase_unavailable')
            else:
                await journey.observe(result, selector=selectors[action])
            if result['status'] in ('observed', 'partial'):
                await journey.observe(revisit, url=url)
            else:
                revisit['reasons'].append('prior_phase_unavailable')
            previous = revisit
    finally:
        await context.close()


def collect(url: str, *, authorized_origin: str, authorization: Mapping[str, object],
            actions: Mapping[str, str] | None = None,
            consent_url: str | None = None, safe_request_paths: Iterable[str] = (),
            notice_selectors: Iterable[str] = (), settle_ms: int = 500) -> dict:
    """Collect a redacted packet after the caller has obtained owner authorization."""
    if not isinstance(authorization, Mapping) or authorization.get('attested') is not True:
        raise ValueError('an explicit authorization attestation is required')
    origin = _origin(authorized_origin)
    if authorized_origin != origin:
        raise ValueError('authorized origin must be an exact canonical origin without a path')
    url = _approved_url(url, origin)
    consent_url = url if consent_url is None else _approved_url(consent_url, origin)
    _require_https(origin)
    if actions is not None and not isinstance(actions, Mapping):
        raise ValueError('actions must map accept, reject or withdraw to explicit selectors')
    actions = {} if actions is None else dict(actions)
    if not set(actions) <= set(ACTIONS):
        raise ValueError('actions must map accept, reject or withdraw to explicit selectors')
    _strings(actions.values(), 'action selectors', limit=3, width=200)
    if 'withdraw' in actions and 'accept' not in actions:
        raise ValueError('withdrawal requires an acceptance selector')
    interactions = authorization.get('interactions')
    if not isinstance(interactions, (list, tuple)):
        raise ValueError('authorization must list the attested interactions')
    interactions = _strings(interactions, 'attested interactions', limit=3, width=8)
    if sorted(interactions) != sorted(actions):
        raise ValueError('attested interactions must match the configured actions')
    paths = _strings(safe_request_paths, 'safe request paths', limit=25, width=200)
    if any(not SAFE_PATH.fullmatch(path) for path in paths):
        raise ValueError('safe request paths must be literal plain paths')
    selectors = _strings(notice_selectors, 'notice selectors', limit=15, width=200)
    if type(settle_ms) is not int or not 0 <= settle_ms <= 2000:
        raise ValueError('settle_ms must be an integer from 0 to 2000')

    phases = ['entry', 'initial'] if url != consent_url else ['initial']
    phases += ['reject', 'revisit_after_reject']
    if 'accept' in actions:
        phases.append('initial_before_accept')
    phases += ['accept', 'revisit_after_accept', 'withdraw', 'revisit_after_withdraw']
    started_at = _now()
    attestation = dict(attested=True, origin=origin, interactions=list(interactions),
                       attested_at=started_at, evidence_status='supplied')
    collector = dict(name='playwright-chromium', revision=_collector_revision())
    packet = dict(schema_version=1, collector=collector, browser=None, authorized_origin=origin,
                  authorization=attestation, started_at=started_at, finished_at=None, settle_ms=settle_ms,
                  observations=[_observation(phase) for phase in phases])
    try:
        asyncio.run(asyncio.wait_for(
            _collect(packet, url, consent_url, actions, frozenset(paths), selectors), 85,
        ))
    except asyncio.TimeoutError:
        for result in packet['observations']:
            if result['status'] in ('not_attempted', 'blocked'):
                result['reasons'].append('collection_deadline')
    except ImportError:
        for result in packet['observations']:
            result['reasons'].append('playwright_dependency_unavailable')
    for result in packet['observations']:
        if result['status'] == 'not_attempted' and not result['reasons']:
            result['reasons'].append('action_not_configured')
        result['page_response_evidence_status'] = 'observed' if result['page_status'] is not None else 'unknown'
        result['storage_evidence_status'] = {
            name: 'unknown' if count is None else 'observed' for name, count in result['storage'].items()
        }
        for notice in result['notices']:
            notice['evidence_status'] = 'observed' if notice['visible_count'] else 'unknown'
    packet['finished_at'] = _now()
    return packet
