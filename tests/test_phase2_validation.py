"""Unit checks for the Phase 2 collector's scope validation."""

import asyncio
import socket
import unittest
from unittest.mock import AsyncMock, patch

from collector.browser import _origin, _public_addresses, _require_public_resolution, collect


class ScopeTests(unittest.TestCase):
    def test_origin(self):
        cases = (
            ("https://Merchant.test/contact", "https://merchant.test"),
            ("https://merchant.test:443/", "https://merchant.test"),
            ("http://127.0.0.1:8123/", "http://127.0.0.1:8123"),
            ("https://[2606:4700::1111]/", "https://[2606:4700::1111]"),
            ("https://user@merchant.test/", None),
            ("https://merchant.test:0/", None),
            ("https://merchant.test:65536/", None),
            ("https://merchant.test./", None),
            ("https://merchant.test\\path", None),
            ("https://127.000.000.001/", None),
            ("https://0x7f000001/", None),
            ("https://2130706433/", None),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                if expected is None:
                    with self.assertRaises(ValueError):
                        _origin(url)
                else:
                    self.assertEqual(_origin(url), expected)

    def test_literal_address_policy(self):
        cases = (
            ("https://1.1.1.1", False, True),
            ("https://[64:ff9b::101:101]", False, True),
            ("http://127.0.0.1:8123", True, True),
            ("http://127.0.0.1:8123", False, False),
            ("https://[64:ff9b::c000:201]", False, False),
            ("https://[64:ff9b::7f00:1]", True, False),
            ("https://100.64.0.1", False, False),
            ("https://198.18.0.1", False, False),
            ("https://224.0.0.1", False, False),
            ("https://[fe80::1]", False, False),
            ("http://merchant.test", True, False),
        )
        for origin, allow_loopback, allowed in cases:
            with self.subTest(origin=origin, allow_loopback=allow_loopback):
                if allowed:
                    _require_public_resolution(origin, allow_loopback)
                else:
                    with self.assertRaises(ValueError):
                        _require_public_resolution(origin, allow_loopback)

    def test_authorization_must_attest_exact_actions_before_collection(self):
        origin = "https://merchant.test"
        actions = {"reject": "#reject"}
        cases = (
            None,
            {"attested": False, "interactions": ["reject"]},
            {"attested": 1, "interactions": ["reject"]},
            {"attested": True},
            {"attested": True, "interactions": []},
            {"attested": True, "interactions": ["accept"]},
            {"attested": True, "interactions": ["reject", "accept"]},
            {"attested": True, "interactions": ["reject", "reject"]},
            {"attested": True, "interactions": "reject"},
        )
        with patch("collector.browser._collect") as run:
            with self.assertRaises(TypeError):
                collect(origin, authorized_origin=origin, actions=actions)
            for authorization in cases:
                with self.subTest(authorization=authorization), self.assertRaises(ValueError):
                    collect(origin, authorized_origin=origin, authorization=authorization, actions=actions)
            run.assert_not_called()


class PublicAddressTests(unittest.IsolatedAsyncioTestCase):
    async def test_dns_answers_must_all_be_public(self):
        cases = (
            (("1.1.1.1", "1.1.1.1", "2606:4700::1111"), ("1.1.1.1", "2606:4700::1111")),
            (("64:ff9b::101:101",), ("64:ff9b::101:101",)),
            (("64:ff9b::c000:201",), None),
            (("1.1.1.1", "64:ff9b::7f00:1"), None),
            (("127.0.0.1",), None),
            (("ff02::1",), None),
            ((), None),
        )
        for addresses, expected in cases:
            answers = [(None, socket.SOCK_STREAM, None, "", (address, 0)) for address in addresses]
            lookup = AsyncMock(return_value=answers)
            with self.subTest(addresses=addresses), patch.object(asyncio.get_running_loop(), "getaddrinfo", lookup):
                if expected is None:
                    with self.assertRaisesRegex(OSError, "non-public resolution"):
                        await _public_addresses("https://merchant.test")
                else:
                    self.assertEqual(await _public_addresses("https://merchant.test"), expected)
                lookup.assert_awaited_once_with("merchant.test", None, type=socket.SOCK_STREAM)
