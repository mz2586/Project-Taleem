"""Tests for the pure-stdlib platform frameworks."""

from __future__ import annotations

import io
import json
import unittest

from taleem_core.platform import correlation
from taleem_core.platform.config import Environment, Settings
from taleem_core.platform.feature_flags import StaticFlagProvider
from taleem_core.platform.i18n import NumeralSystem, default_catalog, render_numerals
from taleem_core.platform.ids import uuid7
from taleem_core.platform.logging import DEFAULT_ALLOW, StructuredLogger, redact
from taleem_core.platform.metrics import Registry
from taleem_core.platform.plugins import Module, ModuleRegistry


class TestConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        s = Settings()
        self.assertEqual(s.default_locale, "ur")  # Urdu-first
        self.assertFalse(s.is_production)

    def test_enabled_flags_parsing(self) -> None:
        s = Settings(enabled_flags_csv="a, b ,c")
        self.assertEqual(s.enabled_flags(), frozenset({"a", "b", "c"}))

    def test_production_flag(self) -> None:
        self.assertTrue(Settings(environment=Environment.PRODUCTION).is_production)


class TestLoggingRedaction(unittest.TestCase):
    def test_allowlist_drops_undeclared_keys(self) -> None:
        out = redact(
            {"event": "x", "child_name": "Ayesha", "guardian_phone": "+92300"}, DEFAULT_ALLOW
        )
        self.assertIn("event", out)
        self.assertNotIn("child_name", out)  # dropped by allow-list
        self.assertNotIn("guardian_phone", out)

    def test_pattern_scrub_on_allowed_string(self) -> None:
        allow = DEFAULT_ALLOW | {"context"}
        out = redact({"context": "contact me at a@b.com or +92 300 1234567"}, allow)
        self.assertNotIn("a@b.com", out["context"])
        self.assertIn("[REDACTED]", out["context"])

    def test_logger_emits_no_pii(self) -> None:
        buf = io.StringIO()
        log = StructuredLogger("test", "INFO", stream=buf)
        log.info("request", path="/health", child_name="Zunaira")
        line = json.loads(buf.getvalue())
        self.assertEqual(line["path"], "/health")
        self.assertNotIn("child_name", line)
        self.assertEqual(line["service"], "test")


class TestFeatureFlags(unittest.TestCase):
    def test_deny_by_default(self) -> None:
        p = StaticFlagProvider()
        self.assertFalse(p.is_enabled("unknown"))

    def test_enable_and_context_override(self) -> None:
        p = StaticFlagProvider({"new_ui"})
        self.assertTrue(p.is_enabled("new_ui"))
        self.assertFalse(p.is_enabled("beta"))
        p.enable_for("beta", "cohort:1")
        self.assertTrue(p.is_enabled("beta", context="cohort:1"))
        self.assertFalse(p.is_enabled("beta", context="cohort:2"))


class TestI18n(unittest.TestCase):
    def test_urdu_first_with_fallback(self) -> None:
        c = default_catalog()
        self.assertEqual(c.translate("app.name", "ur"), "تعلیم")
        self.assertEqual(c.translate("app.name", "en"), "Taleem")
        # Missing locale falls back to en, not a crash.
        self.assertEqual(c.translate("health.ok", "fr"), "Service healthy")

    def test_missing_key_is_visible_not_crash(self) -> None:
        c = default_catalog()
        self.assertEqual(c.translate("does.not.exist"), "⟪does.not.exist⟫")

    def test_eastern_numerals(self) -> None:
        self.assertEqual(render_numerals("2026", NumeralSystem.EASTERN), "۲۰۲۶")
        self.assertEqual(render_numerals("2026", NumeralSystem.WESTERN), "2026")


class TestIds(unittest.TestCase):
    def test_uuid7_shape_and_uniqueness(self) -> None:
        a = uuid7()
        b = uuid7()
        self.assertRegex(
            a, r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        self.assertNotEqual(a, b)

    def test_time_ordering_prefix(self) -> None:
        early = uuid7(now_ms=1000)
        late = uuid7(now_ms=2000)
        # The 48-bit ms timestamp spans the first 12 hex digits (bytes 0-5); compare those.
        self.assertLess(early.replace("-", "")[:12], late.replace("-", "")[:12])


class TestMetrics(unittest.TestCase):
    def test_counter_and_render(self) -> None:
        r = Registry()
        r.inc("taleem_requests_total", method="GET")
        r.inc("taleem_requests_total", method="GET")
        self.assertEqual(r.counter_value("taleem_requests_total", method="GET"), 2.0)
        r.observe("dur_ms", 5.0, path="/x")
        text = r.render()
        self.assertIn('taleem_requests_total{method="GET"} 2', text)
        self.assertIn("dur_ms_count", text)


class TestPlugins(unittest.TestCase):
    def test_registration_and_mount_conflict(self) -> None:
        reg = ModuleRegistry()
        reg.register(Module("a", "/a"))
        reg.register(Module("b", "/b"))
        self.assertEqual(reg.names(), ("a", "b"))
        with self.assertRaises(ValueError):
            reg.register(Module("a", "/c"))  # duplicate name
        with self.assertRaises(ValueError):
            reg.register(Module("d", "/a"))  # mount conflict

    def test_health_aggregation(self) -> None:
        reg = ModuleRegistry()
        reg.register(Module("ok", "/ok", lambda: True))
        reg.register(Module("bad", "/bad", lambda: False))
        self.assertEqual(reg.health(), {"ok": True, "bad": False})


class TestCorrelation(unittest.TestCase):
    def test_ensure_uses_incoming_or_mints(self) -> None:
        cid = correlation.ensure_correlation_id("abc")
        self.assertEqual(cid, "abc")
        self.assertEqual(correlation.get_correlation_id(), "abc")
        minted = correlation.ensure_correlation_id(None)
        self.assertTrue(minted)
        self.assertNotEqual(minted, "abc")


if __name__ == "__main__":
    unittest.main()
