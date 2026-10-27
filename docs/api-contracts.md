# API contracts

## `GET /api/v1/health`

Returns `{ "status": "ok", "service": "api" }` when the API process is responsive.

## `GET /api/v1/health/db`

Executes a lightweight `SELECT 1` query. Success returns `{ "status": "ok", "database": "connected" }`. Database failures return HTTP 503 with `{ "status": "error", "database": "unavailable" }` and never expose connection details.

