"""Tests for the hexagonal ports and their stub adapters."""

from __future__ import annotations

import unittest

from taleem_core.ports.cache import InMemoryCache
from taleem_core.ports.clock import FakeClock
from taleem_core.ports.llm import LLMRequest, StubLLMProvider, Tier, route_tier
from taleem_core.ports.storage import InMemoryObjectStore


class TestLLMPort(unittest.TestCase):
    def test_stub_is_offline_and_deterministic(self) -> None:
        p = StubLLMProvider()
        r = p.complete(LLMRequest(prompt="what is 2+2", tier=Tier.LIGHT, grounding=("math",)))
        self.assertEqual(r.provider, "stub")
        self.assertTrue(r.grounded)
        self.assertIn("stub:light", r.text)

    def test_distress_routes_to_safety_tier_regardless_of_difficulty(self) -> None:
        self.assertEqual(route_tier(distress_adjacent=True, difficulty="easy"), Tier.SAFETY)
        self.assertEqual(route_tier(distress_adjacent=True, difficulty="hard"), Tier.SAFETY)

    def test_normal_tier_routing(self) -> None:
        self.assertEqual(route_tier(distress_adjacent=False, difficulty="easy"), Tier.LIGHT)
        self.assertEqual(route_tier(distress_adjacent=False, difficulty="hard"), Tier.DEEP)


class TestCache(unittest.TestCase):
    def test_set_get_delete(self) -> None:
        c = InMemoryCache()
        c.set("k", 1)
        self.assertEqual(c.get("k"), 1)
        c.delete("k")
        self.assertIsNone(c.get("k"))

    def test_ttl_expiry_with_fake_clock(self) -> None:
        clk = FakeClock(start=100.0)
        c = InMemoryCache(clock=clk)
        c.set("k", "v", ttl_s=10)
        self.assertEqual(c.get("k"), "v")
        clk.advance(11)
        self.assertIsNone(c.get("k"))  # expired


class TestStorage(unittest.TestCase):
    def test_put_returns_content_hash_and_roundtrip(self) -> None:
        s = InMemoryObjectStore()
        digest = s.put("a.txt", b"hello")
        self.assertEqual(len(digest), 64)  # sha256 hex
        self.assertTrue(s.exists("a.txt"))
        self.assertEqual(s.get("a.txt"), b"hello")


if __name__ == "__main__":
    unittest.main()
