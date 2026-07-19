# 39 · Logging

| | |
|---|---|
| **Document ID** | 39 |
| **Owner** | SRE Lead / Head of Security Engineering |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [38 Monitoring](./38-monitoring.md) · [13 Security](../03-security-privacy/13-security-model.md) · [14 Privacy](../03-security-privacy/14-privacy-model.md) · [10 API Design](../02-architecture/10-api-design.md) · [04 NFR](../01-product/04-non-functional-requirements.md) |

## Purpose

This document defines **how Taleem logs**: structured, correlated application logs; the immutable
security/audit log; the strict **no-PII/no-secrets** rule; retention; and the logging pipeline. Logs
must make incidents debuggable and actions auditable **without ever leaking a child's data**.

## Scope

In scope: application logging, audit logging, correlation, PII/secret redaction, retention, and pipeline.
Out of scope: metrics/tracing ([38 Monitoring](./38-monitoring.md)) and privacy lawful basis ([14](../03-security-privacy/14-privacy-model.md)).

---

## 1. Principles

1. **Structured & correlated** — JSON logs with trace/correlation IDs; 100% of requests traceable
   ([04 NFR OBS-01](../01-product/04-non-functional-requirements.md)).
2. **No child PII, no secrets, ever** — a hard rule, enforced by redaction + scanning ([04 NFR OBS-05](../01-product/04-non-functional-requirements.md)).
3. **Audit is immutable** — security/safety/grade/consent actions are tamper-evident ([13 §9](../03-security-privacy/13-security-model.md)).
4. **Right level, low noise** — logs are actionable; no debug spam in production.
5. **Retention-minimised** — kept only as long as needed ([14 §6](../03-security-privacy/14-privacy-model.md)).

## 2. Application logs

| Field | Notes |
|---|---|
| `timestamp`, `level`, `service`, `env` | Standard |
| `traceId`, `spanId`, `correlationId` | Correlate with tracing ([38](./38-monitoring.md)) & error responses ([10 §4](../02-architecture/10-api-design.md)) |
| `studentRef`/`actorRef` | **Pseudonymous only** — never a name ([14 §5](../03-security-privacy/14-privacy-model.md)) |
| `event`, `outcome`, `durationMs` | What happened |

Levels: `ERROR` (actionable failure), `WARN` (degraded), `INFO` (key events), `DEBUG` (off in prod).

## 3. The no-PII / no-secrets rule

- **Redaction at the logging boundary** — known PII/secret fields are dropped/hashed before write.
- **CI log-scanning gate** asserts no PII/secret patterns in log statements ([37 CI/CD](./37-cicd-pipeline.md)).
- Errors carry a **`traceId`, never PII or stack traces to clients** ([10 §4](../02-architecture/10-api-design.md), [13 §4](../03-security-privacy/13-security-model.md)).

## 4. Audit log (immutable)

- **Append-only, tamper-evident** record of authentication events, authorization decisions on sensitive
  resources, **grade overrides, consent changes, safety actions, and privileged admin actions**
  ([13 §9](../03-security-privacy/13-security-model.md), [FR-TNS-004](../01-product/03-functional-requirements.md), [FR-ADM-003](../01-product/03-functional-requirements.md)).
- Stored separately from application logs, with the strictest access controls (safeguarding audit in the
  C4 zone, [15](../03-security-privacy/15-child-safety-framework.md)).

## 5. Pipeline & retention

- Logs ship to a central, access-controlled store; **retention differs by class** — application logs
  short, audit logs per security/legal policy, all PII-minimised ([14 §6](../03-security-privacy/14-privacy-model.md)).
- Access to logs is least-privilege and itself audited.

## 6. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Child PII in logs | Privacy breach | Boundary redaction + CI scanning + pseudonymous refs. |
| R-2 | Secrets in logs | Credential leak | Redaction + secret scanning. |
| R-3 | Audit log tampered | Lost accountability | Append-only, tamper-evident, isolated store. |
| R-4 | Log noise hides incidents | Slow response | Level discipline, actionable logging. |

## Open questions

- **Log store** choice within cost/residency constraints ([36](../02-architecture/36-infrastructure-architecture.md)).
- **Audit retention periods** per action class (legal input) ([14 O-2](../03-security-privacy/14-privacy-model.md)).
- **Redaction library**/approach across Python + TypeScript.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial logging: structured correlated logs, hard no-PII/no-secrets rule with CI scanning, immutable audit log, retention-minimised pipeline. | SRE / Security Eng |
