"""Bounded anonymous Chromium observations for owner-authorized pages."""

import asyncio
from collections.abc import Iterable, Mapping
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import ipaddress
import json
import re
import socket
from urllib.parse import urlsplit

from .transport import PinnedProxy


ACTIONS = ('accept', 'reject', 'withdraw')
NAVIGATION_MS = 6500
REQUEST_MS = 4000
MAX_REQUESTS = 120
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
        ord(char) < 33 or char == '\\' for char in url
    ):
        raise ValueError('invalid HTTP(S) URL')
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as error:
        raise ValueError('invalid HTTP(S) URL') from error
    if parts.scheme not in ('https', 'http') or not host or parts.username is not None or port == 0:
        raise ValueError('invalid HTTP(S) URL')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        labels = host.split('.')
        if len(labels) < 2 or labels[-1].isdigit() or any(
            not HOST_LABEL.fullmatch(label) or label.startswith('-') or label.endswith('-')
            for label in labels
        ):
            raise ValueError('invalid HTTP(S) host') from None
        if labels[-1].startswith('0x'):
            raise ValueError('invalid HTTP(S) host')
        authority = host
    else:
        authority = f'[{host}]' if address.version == 6 else host
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


def _require_public_resolution(origin, allow_loopback):
    parts = urlsplit(origin)
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        address = None
    if address is not None and address.is_loopback and allow_loopback:
        return
    if parts.scheme != 'https':
        raise ValueError('public sites require HTTPS and fixtures require explicit loopback permission')
    if address is not None and (not address.is_global or address.is_multicast):
        raise ValueError('target must be public or an explicitly authorized literal loopback fixture')
    return


async def _public_addresses(origin):
    host = urlsplit(origin).hostname
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        loop = asyncio.get_running_loop()
        answers = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), 3)
        addresses = tuple(dict.fromkeys(ipaddress.ip_address(item[4][0]) for item in answers))
        if not addresses or any(not address.is_global or address.is_multicast for address in addresses):
            raise OSError('non-public resolution')
        return tuple(str(address) for address in addresses)
    return (str(address),)


def _strings(values, label, *, limit, width):
    if isinstance(values, str):
        raise ValueError(f'{label} must be a collection of strings')
    values = tuple(values)
    if len(values) > limit or any(not isinstance(value, str) or not value or len(value) > width for value in values):
        raise ValueError(f'invalid {label}')
    return values


def _now():
    return datetime.now(timezone.utc).isoformat()


def _observation(phase):
    return dict(phase=phase, status='not_attempted', reasons=[], page_status=None,
                requests=[], forms=[], notices=[], storage={'cookies': None, 'local': None, 'session': None})


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
    const formNodes = limited(forms);
    return {
        forms: formNodes.map((form) => ({
            visible: visible(form),
            described_by_visible_element: describedBy(form),
            fields: limited(controls(form)).map((field) => ({
                tag: field.tagName.toLowerCase(),
                type: field.type,
                required: field.required,
                labeled: Array.from(field.labels || []).some(visible) || Boolean(field.getAttribute('aria-label')),
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
        except self.errors + (TimeoutError,):
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
        incomplete = dict.fromkeys(event['reason'] or 'request_pending' for event in result['requests']
                                   if event['disposition'] != 'observed')
        result['reasons'].extend(reason for reason in incomplete if reason not in result['reasons'])
        if result['status'] == 'observed' and result['reasons']:
            result['status'] = 'partial'
        self.current = None
        self.navigation = None


async def _collect(packet, url, consent_url, actions, paths, selectors):
    from playwright.async_api import Error, async_playwright

    origin = packet['authorized_origin']
    observations = {result['phase']: result for result in packet['observations']}
    try:
        addresses = await _public_addresses(origin)
    except (OSError, TimeoutError):
        for result in observations.values():
            result['reasons'].append('public_dns_check_failed')
        return

    journey = _Journey(origin, paths, selectors, packet['settle_ms'], (Error,))
    try:
        async with AsyncExitStack() as stack:
            playwright = await stack.enter_async_context(async_playwright())
            parts = urlsplit(origin)
            port = parts.port or (443 if parts.scheme == 'https' else 80)
            host = f'[{parts.hostname}]' if ':' in parts.hostname else parts.hostname
            proxy = await stack.enter_async_context(PinnedProxy(f'{host}:{port}', addresses, port))
            journey.transport = await playwright.request.new_context(proxy={'server': proxy})
            stack.push_async_callback(journey.transport.dispose)
            browser = await playwright.chromium.launch(args=BROWSER_ARGS, chromium_sandbox=True, timeout=8000)
            packet['browser'] = {'engine': 'chromium', 'version': browser.version}
            try:
                if url != consent_url:
                    await _branch(browser, journey, observations, url, 'entry', (), actions)
                reject = ('reject',) if 'reject' in actions else ()
                await _branch(browser, journey, observations, consent_url, 'initial', reject, actions)
                if 'accept' in actions:
                    sequence = ('accept', 'withdraw') if 'withdraw' in actions else ('accept',)
                    observations['initial_before_accept'] = _observation('initial_before_accept')
                    packet['observations'].insert(
                        packet['observations'].index(observations['accept']), observations['initial_before_accept'],
                    )
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


def collect(url: str, *, authorized_origin: str, actions: Mapping[str, str] | None = None,
            consent_url: str | None = None, safe_request_paths: Iterable[str] = (),
            notice_selectors: Iterable[str] = (), settle_ms: int = 500,
            allow_loopback: bool = False) -> dict:
    """Collect a redacted packet after the caller has obtained owner authorization."""
    origin = _origin(authorized_origin)
    if authorized_origin != origin:
        raise ValueError('authorized origin must be an exact canonical origin without a path')
    _require_public_resolution(origin, allow_loopback is True)
    url = _approved_url(url, origin)
    consent_url = url if consent_url is None else _approved_url(consent_url, origin)
    if actions is None:
        actions = {}
    if not isinstance(actions, Mapping) or not set(actions) <= set(ACTIONS):
        raise ValueError('actions must map accept, reject or withdraw to explicit selectors')
    _strings(actions.values(), 'action selectors', limit=3, width=200)
    if 'withdraw' in actions and 'accept' not in actions:
        raise ValueError('withdrawal requires an acceptance selector')
    paths = _strings(safe_request_paths, 'safe request paths', limit=25, width=200)
    if any(not SAFE_PATH.fullmatch(path) for path in paths):
        raise ValueError('safe request paths must be literal plain paths')
    selectors = _strings(notice_selectors, 'notice selectors', limit=15, width=200)
    if type(settle_ms) is not int or not 0 <= settle_ms <= 2000:
        raise ValueError('settle_ms must be an integer from 0 to 2000')

    phases = ['entry', 'initial'] if url != consent_url else ['initial']
    phases += ['reject', 'revisit_after_reject', 'accept', 'revisit_after_accept',
               'withdraw', 'revisit_after_withdraw']
    packet = dict(schema_version=1, collector='playwright-chromium', browser=None, authorized_origin=origin,
                  started_at=_now(), finished_at=None, settle_ms=settle_ms,
                  observations=[_observation(phase) for phase in phases])
    try:
        asyncio.run(asyncio.wait_for(
            _collect(packet, url, consent_url, dict(actions), frozenset(paths), selectors), 85,
        ))
    except TimeoutError:
        for result in packet['observations']:
            if result['status'] in ('not_attempted', 'blocked'):
                result['reasons'].append('collection_deadline')
    except ImportError:
        for result in packet['observations']:
            result['reasons'].append('playwright_dependency_unavailable')
    for result in packet['observations']:
        if result['status'] == 'not_attempted' and not result['reasons']:
            result['reasons'].append('action_not_configured')
    packet['finished_at'] = _now()
    return packet
