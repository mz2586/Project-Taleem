# 38 · Monitoring

| | |
|---|---|
| **Document ID** | 38 |
| **Owner** | SRE Lead / Head of Platform Engineering |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [39 Logging](./39-logging.md) · [37 CI/CD](./37-cicd-pipeline.md) · [35 Deployment](../02-architecture/35-deployment-architecture.md) · [04 NFR](../01-product/04-non-functional-requirements.md) · [13 Security](../03-security-privacy/13-security-model.md) · [15 Child Safety](../03-security-privacy/15-child-safety-framework.md) |

## Purpose

This document defines **how Taleem is observed in production**: metrics, distributed tracing, SLOs and
error budgets, alerting, dashboards, and the special monitoring of child-safety signals. It operationalises
the availability/performance targets of [04 NFR §7/§12](../01-product/04-non-functional-requirements.md).

## Scope

In scope: metrics, tracing, SLO/alerting, dashboards, and safety/security monitoring. Out of scope:
log content/pipeline ([39 Logging](./39-logging.md)) and infra provisioning ([36 Infrastructure](../02-architecture/36-infrastructure-architecture.md)).

---

## 1. Principles

1. **SLO-driven** — we monitor the learner's experience against explicit SLOs, not vanity metrics
   ([04 NFR AVAIL/PERF](../01-product/04-non-functional-requirements.md)).
2. **The core path is sacred** — login → lesson → submit has the tightest SLOs and alerting.
3. **Golden signals per service** — latency, traffic, errors, saturation ([04 NFR OBS-02](../01-product/04-non-functional-requirements.md)).
4. **Safety is monitored** — child-safety signals have first-class alerting ([15](../03-security-privacy/15-child-safety-framework.md)).
5. **No PII in telemetry** ([04 NFR OBS-05](../01-product/04-non-functional-requirements.md)).

## 2. Metrics

- **RED** (Rate, Errors, Duration) for request services; **USE** (Utilisation, Saturation, Errors) for
  resources; queue depth for workers; connection count for realtime ([08 §9.1](../02-architecture/08-system-architecture.md)).
- **Business/learning metrics** (north-star, mastery, delivery) via analytics ([31](../06-portals/31-analytics-platform.md)),
  separate from operational metrics.
- **AI Teacher** metrics: first-token latency, tier mix, cost/turn, safety-block rate ([24 §9](../05-education/24-ai-teacher-specification.md)).

## 3. Distributed tracing

- End-to-end traces across the core path, propagated through the **outbox/event** flow so async work is
  correlated ([04 NFR OBS-03](../01-product/04-non-functional-requirements.md), [08 §6.2](../02-architecture/08-system-architecture.md)).
- Trace IDs correlate to logs ([39](./39-logging.md)) and error responses ([10 §4](../02-architecture/10-api-design.md)).

## 4. SLOs & error budgets

| SLO | Target | Source |
|---|---|---|
| Core-path availability | 99.9% | [04 NFR AVAIL-01](../01-product/04-non-functional-requirements.md) |
| API latency p95 | < 300 ms | [04 NFR PERF-01](../01-product/04-non-functional-requirements.md) |
| Lesson FCP (3G) | < 3 s | [04 NFR PERF-02](../01-product/04-non-functional-requirements.md) |
| AI first-token p95 | < 2.5 s | [04 NFR PERF-05](../01-product/04-non-functional-requirements.md) |

- **Error budgets** govern release velocity: burning the budget **auto-halts** the canary ramp
  ([35 §4](../02-architecture/35-deployment-architecture.md)).
- Alerts fire **before** an SLA breach ([04 NFR OBS-04](../01-product/04-non-functional-requirements.md)).

## 5. Alerting & on-call

- **Symptom-based, actionable alerts** with a **runbook per alert** ([04 NFR MNT-05](../01-product/04-non-functional-requirements.md));
  no noisy/unactionable alerts.
- **Severity tiers**; **any child-safety-impacting signal is top severity** and pages Trust & Safety
  ([15 §9](../03-security-privacy/15-child-safety-framework.md), [13 §10](../03-security-privacy/13-security-model.md)).
- Game-days validate alerting and runbooks.

## 6. Dashboards

- **Core-path SLO dashboard** (the one everyone watches), per-service golden-signal dashboards, AI cost
  & safety dashboard, and a delivery/notification dashboard.
- Dashboards are **scoped** and contain **no child PII**.

## 7. Safety & security monitoring

- **Safety signals** (AI block rate, flag volume, escalation SLA adherence) monitored with alerts
  ([15](../03-security-privacy/15-child-safety-framework.md)).
- **Security anomalies** (auth anomalies, refresh reuse, privilege spikes) feed detection ([13 §9](../03-security-privacy/13-security-model.md)).

## 8. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | SLA breach undetected | Learners affected silently | SLO alerting before breach + core-path dashboard. |
| R-2 | Alert fatigue | Missed real incident | Symptom-based, actionable, runbook-backed alerts. |
| R-3 | Safety signal missed | Child harm | First-class safety alerting to Trust & Safety. |
| R-4 | PII in telemetry | Privacy breach | No-PII policy + scanning ([39](./39-logging.md)). |

## Open questions

- **Observability stack** choice (OpenTelemetry + backend) within cost budget.
- **Canary auto-halt** thresholds per SLO ([35](../02-architecture/35-deployment-architecture.md)).
- **Learner-perceived RUM** collection without privacy compromise.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial monitoring: metrics (RED/USE), tracing across outbox, SLOs/error budgets, actionable alerting + runbooks, dashboards, safety/security monitoring. | SRE Lead |
