# Architecture

SAHAKAR–SEVA is a small monorepo: a React/TypeScript web client and a versioned FastAPI service over
PostgreSQL/PostGIS, orchestrated for local use with Docker Compose. The API owns all configuration,
persistence, validation and error shaping; schema changes go only through Alembic migrations.

This document describes the **current** runtime. For the present feature inventory see
[`PROJECT_CURRENT_STATE.md`](PROJECT_CURRENT_STATE.md); for byte-level ledger formats see
[`architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md`](architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md).

## System overview

```mermaid
flowchart LR
  subgraph Client["apps/web (React + Vite)"]
    UI[Pages and components]
    RV[Offline receipt verifier\nlib/receiptVerify.ts]
  end
  subgraph API["services/api (FastAPI)"]
    R[/api/v1 routers/]
    SVC[Services\nbooking / job / dispute / trust / pricing / demo]
    TRUST[trust: crypto, chain, anchoring,\ntimestamping, integrity, pricing]
    WORKER[(anchor background worker)]
  end
  DB[(PostgreSQL 16 + PostGIS)]
  TSA[External RFC 3161 TSA\noptional, pinned CA]

  UI -->|bearer token| R --> SVC --> DB
  SVC --> TRUST --> DB
  WORKER -->|checkpoint + submit| TRUST
  TRUST -. only 32-byte digest + nonce .-> TSA
  UI -->|download receipt| R
  RV -. verifies offline, no server .-> RV
```

Authentication is verified server-side on every protected request: either a Supabase bearer token
(HS256 shared secret, or server-side `/auth/v1/user` validation) or, for local demos only, a
development identity token. With neither configured the API fails closed with `503
AUTH_NOT_CONFIGURED`.

## Marketplace request path

```mermaid
flowchart LR
  A[Customer / Worker] --> B[React client]
  B -->|HTTPS + bearer| C[FastAPI /api/v1]
  C --> D[Auth dependency\nSupabase or dev-auth]
  D --> E[Service layer]
  E --> F[(PostgreSQL / PostGIS)]
  F --> E --> C --> B
```

## Direct hire lifecycle

```mermaid
stateDiagram-v2
  [*] --> requested: customer requests a slot
  requested --> confirmed: worker accepts (overlap re-checked)
  requested --> declined: worker declines
  requested --> cancelled: customer/worker cancels
  confirmed --> in_progress: worker starts
  confirmed --> cancelled: cancel
  in_progress --> completed: customer confirms completion
  confirmed --> disputed: either party disputes
  in_progress --> disputed
  completed --> disputed
  completed --> [*]
```

Discovery uses PostGIS geography radius queries. A worker-side exclusion constraint
(`ex_bookings_worker_no_overlap`, migration `0004`) is the database-level guarantee that a worker can
never hold two overlapping confirmed bookings; `accept` row-locks the worker profile and re-checks
overlap before relying on it.

## Job posting flow

```mermaid
flowchart TD
  P[Customer posts job\nskill, locality, budget] --> Q[Open job board]
  Q --> R[Worker applies]
  R --> S[Customer selects an applicant]
  S --> T[Shared booking created\norigin=job]
  T --> U[Worker accepts -> confirmed]
  U --> V[Other applications auto-rejected]
  V --> W[Same booking lifecycle as direct hire]
```

## Financial agreement and simulated settlement

```mermaid
sequenceDiagram
  participant C as Customer
  participant W as Worker
  participant API as FastAPI
  participant FP as Pricing engine (active fee policy)
  participant L as Ledger + event chain

  C->>API: request booking
  API->>FP: price with active fee policy (0006)
  FP-->>API: quote v1 (line items, bearer, ceiling checked)
  API->>L: record quote + customer acceptance (hash-chained)
  W->>API: accept booking
  API->>L: worker acceptance + booking_confirmed event
  C->>API: confirm completion
  API->>L: booking_completed + ONE immutable simulated settlement
  API->>L: balanced double-entry ledger transaction
  Note over L: settlement.is_simulated = true\n"SIMULATED PAYMENT — NO REAL MONEY TRANSFERRED"
```

Pricing is never hardcoded. Each booking stores the fee policy id, version, definition hash and line
items of its accepted quote. Changing the active policy affects only new quotes. Charges are recorded
only on completion; cancellations record none; disputes may record a reversal.

## External anchoring (optional)

No network call ever runs inside a database transaction. Checkpoints are an outbox: created inside a
short transaction, submitted to the TSA with no transaction open, then the verified result is recorded
in a second short transaction.

```mermaid
stateDiagram-v2
  [*] --> LOCAL_ONLY: no TSA configured
  [*] --> ANCHOR_PENDING: TSA configured
  LOCAL_ONLY --> ANCHOR_PENDING: TSA later configured (promote)
  ANCHOR_PENDING --> ANCHOR_SUBMITTED: digest + nonce sent
  ANCHOR_SUBMITTED --> EXTERNALLY_ANCHORED: token verifies against pinned CA
  ANCHOR_SUBMITTED --> PROOF_INVALID: token fails verification
  ANCHOR_SUBMITTED --> ANCHOR_PENDING: unavailable -> backoff retry
  ANCHOR_PENDING --> ANCHOR_FAILED: attempts exhausted
  PROOF_INVALID --> ANCHOR_PENDING: operator retry
  ANCHOR_FAILED --> ANCHOR_PENDING: operator retry
  EXTERNALLY_ANCHORED --> [*]
```

Only a 32-byte SHA-256 checkpoint digest and a random nonce leave the system. `TSA_CA_FILE` is the
**pinned** trust anchor; a certificate inside a TSA response is never trusted on its own. Booking
completion never waits for anchoring.

This is **not** a blockchain and the system is **not** decentralized. Independent assurance comes from
(a) an RFC 3161 timestamp issued by a third party over a checkpoint digest, and (b) receipts that
participants hold and can re-verify offline — not from distributed consensus.

## Trust/evidence verification

```mermaid
flowchart LR
  subgraph Evidence
    EV[Event chain\nSHA-256, domain-separated, RFC 8785]
    CP[Merkle checkpoints\nRFC 9162 inclusion proofs]
    LD[Double-entry ledger\ndebits == credits]
  end
  EV --> V1[integrity.verify_records\nserver-side]
  CP --> V1
  LD --> V1
  R[Downloaded receipt JSON] --> V2[scripts/verify_receipt.py\noffline, no server code]
  R2[Earlier receipt copy] --> V2
  V2 --> OUT{verified / local-only / failed}
```

## Deployment (local)

Docker Compose runs three services: `db` (PostGIS, host port `55432`), `api` (FastAPI on `8000`,
applies migrations on start), and `web` (Vite dev server on `5173`). `scripts/dev_up.sh` pins the
local database credentials for that command, applies migrations, seeds the taxonomy and activates the
labelled illustrative fee policy, then health-checks the API. See the root `README.md` quick start.
