import http.client
import importlib.util
import re
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


def load_fixture_module():
    path = Path(__file__).resolve().parents[1] / "benchmark" / "sites" / "serve.py"
    spec = importlib.util.spec_from_file_location("dpdp_fixture_sites", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResourceURLs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attributes):
        for name, value in attributes:
            if name in {"href", "src", "action", "poster", "data", "srcset", "formaction"}:
                self.urls.append(value)


class FixtureSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture_module()
        cls.server = cls.fixture.build_server(0)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)
        cls.server.server_close()

    def request(self, path, method="GET", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.headers, response.read().decode()
        finally:
            conn.close()

    def test_loopback_ephemeral_port_and_routes(self):
        self.assertEqual(self.server.server_address, ("127.0.0.1", self.server.server_port))
        self.assertGreater(self.server.server_port, 0)
        for route, (_, content_type) in self.fixture.ROUTES.items():
            with self.subTest(route=route):
                status, headers, body = self.request(route)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], content_type)
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertTrue(body.strip())
                self.assertEqual(self.request(route, method="HEAD")[2], "")
        self.assertEqual(self.request("/missing")[0], 404)
        self.assertEqual(self.request("/../serve.py")[0], 404)

    def test_blocked_route_returns_no_policy_and_requires_no_spoofing(self):
        for agent in ("Fixture Fetcher", "Fixture Browser"):
            with self.subTest(agent=agent):
                status, headers, body = self.request(
                    "/policy/blocked", headers={"User-Agent": agent}
                )
                self.assertEqual(status, 403)
                self.assertTrue(headers["Content-Type"].startswith("text/plain"))
                self.assertIn("policy response unavailable", body)

    def test_event_endpoint_accepts_only_fixed_synthetic_fields(self):
        for query in ("source=early&event=load", "source=gated&event=accept"):
            self.assertEqual(self.request(f"/events/optional?{query}")[0], 204)
        for query in (
            "",
            "source=other&event=load",
            "source=gated&event=unknown",
            "source=gated&event=load&value=extra",
            "source=gated&event=load&value=",
            "source=gated&source=early&event=load",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.request(f"/events/optional?{query}")[0], 400)
        self.assertEqual(
            self.request("/events/optional?source=early&event=load", method="POST")[0], 405
        )

    def test_consent_controls_and_dynamic_shell_are_wired(self):
        for fixture in ("early", "gated"):
            _, _, html = self.request(f"/consent/{fixture}")
            self.assertIn(f'data-consent-fixture="{fixture}"', html)
            self.assertIn('data-choice="granted"', html)
            self.assertEqual(html.count('data-choice="denied"'), 2)
            self.assertIn('data-choice="reset"', html)
            self.assertIn('src="/assets/consent.js"', html)
        _, _, script = self.request("/assets/consent.js")
        self.assertIn("localStorage.getItem", script)
        self.assertIn("localStorage.removeItem", script)
        self.assertIn("localStorage.setItem", script)
        _, _, shell = self.request("/dynamic")
        self.assertIn('<div id="contact-shell"></div>', shell)
        self.assertNotIn("<form", shell)
        _, _, dynamic = self.request("/assets/dynamic.js")
        self.assertIn('document.createElement("form")', dynamic)
        self.assertIn("event.preventDefault()", dynamic)

    def test_active_resources_are_same_origin_and_vendor_reference_is_inert(self):
        for route in self.fixture.ROUTES:
            status, headers, body = self.request(route)
            self.assertEqual(status, 200)
            csp = headers["Content-Security-Policy"]
            for directive in ("default-src 'none'", "script-src 'self'", "connect-src 'self'", "form-action 'none'"):
                self.assertIn(directive, csp)
            if headers["Content-Type"].startswith("text/html"):
                parser = ResourceURLs()
                parser.feed(body)
                for url in parser.urls:
                    parts = urlsplit(url)
                    self.assertFalse(parts.scheme or parts.netloc)
                    self.assertTrue(url.startswith("/"))
            else:
                self.assertIsNone(re.search(r"https?://|wss?://", body))
        _, _, consent_js = self.request("/assets/consent.js")
        self.assertIn('fetch(`/events/optional?', consent_js)
        self.assertNotIn("fetch(", self.request("/assets/dynamic.js")[2])
        _, _, unknown = self.request("/unknown")
        self.assertIn("https://measurement.example.test/optional.js", unknown)
        self.assertIn("intake.invalid", unknown)


if __name__ == "__main__":
    unittest.main()
