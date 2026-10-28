# Documentation Index

This repository accumulated documentation across several development phases. This index tells a
reviewer **which documents describe the current build** and which are **development history**. Nothing
has been deleted; historical records (including earlier security findings and test counts) are
preserved as written.

**Start here:** [`../README.md`](../README.md) → [`JUDGE_REVIEW_GUIDE.md`](JUDGE_REVIEW_GUIDE.md) →
[`PROJECT_CURRENT_STATE.md`](PROJECT_CURRENT_STATE.md).

## Current, authoritative

These describe the build on `shresthBranch` and are kept in sync with the code.

| Document | Purpose |
|---|---|
| [`PROJECT_CURRENT_STATE.md`](PROJECT_CURRENT_STATE.md) | Present-day source of truth: commit, migration head, feature inventory, API, routes, limitations |
| [`JUDGE_REVIEW_GUIDE.md`](JUDGE_REVIEW_GUIDE.md) | Five-minute evaluation path + claim→evidence map |
| [`architecture.md`](architecture.md) | System architecture and runtime flows (Mermaid) |
| [`SECURITY_AND_TRUST_MODEL.md`](SECURITY_AND_TRUST_MODEL.md) | Threat model, trust boundaries, and the hidden-payment objection answered |
| [`BUSINESS_MODEL.md`](BUSINESS_MODEL.md) | Product/revenue model and assumptions (truthful, unvalidated) |
| [`TESTING_AND_EVIDENCE.md`](TESTING_AND_EVIDENCE.md) | Executed test results with commands and environment |
| [`architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md`](architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md) | Byte-level ledger/checkpoint/receipt formats; matches `app/trust/` |
| [`architecture/REVENUE_AND_RETENTION_MODEL.md`](architecture/REVENUE_AND_RETENTION_MODEL.md) | Detailed revenue/retention design behind `BUSINESS_MODEL.md` |
| [`contracts/MVP_MARKETPLACE_CONTRACT.md`](contracts/MVP_MARKETPLACE_CONTRACT.md) | Marketplace API/behaviour contract (current marketplace routers) |
| [`contracts/TRUST_LEDGER_API_CONTRACT.md`](contracts/TRUST_LEDGER_API_CONTRACT.md) | Trust/agreement/evidence API contract (current trust router) |
| [`contracts/PHASE_3A_DATA_CONTRACT.md`](contracts/PHASE_3A_DATA_CONTRACT.md) | Service taxonomy data contract (still used by the seeder) |
| [`audits/LIVE_DEMO_RUNBOOK.md`](audits/LIVE_DEMO_RUNBOOK.md) | Step-by-step marketplace demo script |
| [`audits/TRUST_LEDGER_DEMO_RUNBOOK.md`](audits/TRUST_LEDGER_DEMO_RUNBOOK.md) | Pricing/ledger/receipt-verification demo script |
| [`audits/TRUST_LEDGER_IMPLEMENTATION_REPORT.md`](audits/TRUST_LEDGER_IMPLEMENTATION_REPORT.md) | Trust-ledger implementation notes |
| [`audits/TRUST_LEDGER_SECURITY_AND_INTEGRITY_TESTS.md`](audits/TRUST_LEDGER_SECURITY_AND_INTEGRITY_TESTS.md) | Adversarial/integrity test catalogue for the ledger |
| [`audits/FINAL_GITHUB_SUBMISSION_READINESS.md`](audits/FINAL_GITHUB_SUBMISSION_READINESS.md) | This hardening pass's final readiness audit |

## Still-accurate background / reference

Useful context that remains broadly correct, though superseded in places by the current docs above.

| Document | Notes |
|---|---|
| [`SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md`](SAHAKAR_SEVA_MASTER_PROJECT_BLUEPRINT.md) | Original product vision and long-term plan; aspirational scope beyond the current build |
| [`DECISIONS.md`](DECISIONS.md) | Architecture decision log |
| [`DATABASE_BASELINE_AND_HANDSHAKE.md`](DATABASE_BASELINE_AND_HANDSHAKE.md) | Database baseline conventions |
| [`contracts/PHASE_2_TECHNICAL_CONTRACT.md`](contracts/PHASE_2_TECHNICAL_CONTRACT.md) | Phase 2 contract; foundation still largely reflected in code |

## Historical phase reports (preserved as-is)

Point-in-time reports. Their test counts, dates and status claims describe **the phase they were
written in**, not the current build. Treat `PROJECT_CURRENT_STATE.md` as current.

- `PHASE_2_GATE_G2_REPORT.md`, `PHASE_2_TECHNICAL_CONTRACT.md` (root copy)
- `audits/PHASE_2_FULL_AUDIT_REPORT.md`, `audits/PHASE_2_REMEDIATION_REPORT.md`,
  `audits/PHASE_2_DATABASE_AUDIT.md`, `audits/PHASE_2_ROUTE_MATRIX.md`,
  `audits/PHASE_2_INTEGRATION_CHECKLIST.md`, `audits/PHASE_2_FIX_PRIORITY.md`,
  `audits/PHASE_2_FINAL_RELEASE_GATE.md`
- `audits/FINAL_HACKATHON_MVP_IMPLEMENTATION.md`, `audits/CURRENT_PROJECT_IMPLEMENTATION_STATUS.md`,
  `audits/FULL_STACK_INTEGRATION_AUDIT.md`, `audits/LOCAL_DEVELOPMENT_READINESS.md`,
  `audits/REMAINING_DEVELOPMENT_ROADMAP.md`
- `plans/2026-10-27-phase2-database-implementation.md`
- `HANDOFF.md`, `OWNERSHIP_MAP.md`, `TEAM_KICKOFF_MESSAGE.md`
- `contracts/phase2.openapi.yaml` — Phase 2 OpenAPI snapshot (the live `/openapi.json` is authoritative)

## Internal team-coordination prompts (historical)

Written to brief individual contributors during development; not product documentation.

- `SHRESTH_DATABASE_ANTIGRAVITY_PROMPT.md`, `PRIYANSHU_BACKEND_ANTIGRAVITY_PROMPT.md`,
  `DHWANIT_FRONTEND_ANTIGRAVITY_PROMPT.md`

## Outdated / superseded stubs

Early Phase 1 stubs kept only for history. **Do not rely on these for the current build.**

| Document | Superseded by |
|---|---|
| [`api-contracts.md`](api-contracts.md) | live `/openapi.json`, `contracts/MVP_MARKETPLACE_CONTRACT.md`, `contracts/TRUST_LEDGER_API_CONTRACT.md` |

> Note: the former Phase 1 `architecture.md` stub was replaced in this pass by the current
> architecture document at the same path (`architecture.md`).

The root `README.md` was rewritten in this pass to describe the current product; earlier README
content described the Phase 1 foundation only.
