"""Observability, logging, tracing, health, and error-contract unit tests (goals #14–#16)."""

from __future__ import annotations

import io
import json
import unittest

from taleem_core.contexts.health.service import Check, HealthService
from taleem_core.platform import errors
from taleem_core.platform.logging import StructuredLogger
from taleem_core.platform.metrics import Registry
from taleem_core.platform.tracing import span


class TestTracing(unittest.TestCase):
    def test_span_records_duration_metric(self) -> None:
        # The global registry accrues a span-duration observation.
        from taleem_core.platform.metrics import registry

        before = registry().render()
        with span("unit.test", attr="x") as s:
            s.set("more", "y")
        after = registry().render()
        self.assertIn("taleem_span_duration_ms", after)
        self.assertNotEqual(before, after)


class TestHealthService(unittest.TestCase):
    def test_ready_degrades_when_a_check_fails(self) -> None:
        svc = HealthService("9.9.9", checks=[Check("db", lambda: False), Check("ok", lambda: True)])
        ok, body = svc.ready()
        self.assertFalse(ok)
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["checks"], {"db": False, "ok": True})

    def test_live_reports_version(self) -> None:
        self.assertEqual(HealthService("1.2.3").live(), {"status": "ok", "version": "1.2.3"})


class TestLoggingLevels(unittest.TestCase):
    def test_debug_suppressed_below_threshold(self) -> None:
        buf = io.StringIO()
        log = StructuredLogger("t", "INFO", stream=buf)
        log.debug("hidden")
        self.assertEqual(buf.getvalue(), "")  # below threshold, not emitted

    def test_error_and_warn_emitted(self) -> None:
        buf = io.StringIO()
        log = StructuredLogger("t", "INFO", stream=buf)
        log.warn("w", outcome="degraded")
        log.error("e", error_code="BOOM")
        lines = [json.loads(line) for line in buf.getvalue().splitlines()]
        self.assertEqual([x["level"] for x in lines], ["WARN", "ERROR"])
        self.assertEqual(lines[1]["error_code"], "BOOM")


class TestErrorContract(unittest.TestCase):
    def test_problem_helpers_status_and_code(self) -> None:
        self.assertEqual(errors.not_found().status, 404)
        self.assertEqual(errors.forbidden().status, 403)
        self.assertEqual(errors.unauthorized().status, 401)
        v = errors.validation_error("bad", [{"field": "x", "message": "required"}])
        self.assertEqual(v.status, 422)
        self.assertEqual(v.code, "VALIDATION_FAILED")

    def test_problem_to_dict_shape(self) -> None:
        body = errors.not_found("missing").to_dict("/v1/x")
        self.assertEqual(body["status"], 404)
        self.assertEqual(body["instance"], "/v1/x")
        self.assertEqual(body["detail"], "missing")


class TestMetricsHistogram(unittest.TestCase):
    def test_histogram_sum_and_count(self) -> None:
        r = Registry()
        r.observe("lat", 2.0, path="/a")
        r.observe("lat", 3.0, path="/a")
        text = r.render()
        self.assertIn("lat_sum", text)
        self.assertIn("lat_count", text)


if __name__ == "__main__":
    unittest.main()
