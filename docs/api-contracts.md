> **Historical (Phase 1).** This stub documents only the health endpoints from the original
> foundation. The authoritative API is the live `/openapi.json` (Swagger at `/docs`), with behaviour
> contracts in [`contracts/MVP_MARKETPLACE_CONTRACT.md`](contracts/MVP_MARKETPLACE_CONTRACT.md) and
> [`contracts/TRUST_LEDGER_API_CONTRACT.md`](contracts/TRUST_LEDGER_API_CONTRACT.md). Kept for history.

# API contracts

## `GET /api/v1/health`

Returns `{ "status": "ok", "service": "api" }` when the API process is responsive.

## `GET /api/v1/health/db`

Executes a lightweight `SELECT 1` query. Success returns `{ "status": "ok", "database": "connected" }`. Database failures return HTTP 503 with `{ "status": "error", "database": "unavailable" }` and never expose connection details.

