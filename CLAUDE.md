# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this is

**ReBridge Backend (v1)** — an AI-assisted returns-grading and routing system. A
returned item is photographed, graded by a vision-model cascade, given a signed
tamper-evident Product Health Card, routed to the best disposition by unit
economics (resell / refurb / peer-to-peer / donate), and matched to likely
buyers. Low-confidence grades go to a human review queue.

## Architecture: 3 packages, one-way dependency

The repo is a Python monorepo with a strict dependency direction
`api -> service -> data`. Never import "up" that chain.

```
rebridge_data/      Interfaces (ABCs) + boto3-backed concretes.
                    THE ONLY package allowed to import boto3.
rebridge_service/   Pure business logic, programmed against rebridge_data
                    interfaces. NO boto3, NO web framework. Framework-free.
rebridge_api/       FastAPI routers, Cognito auth, Lambda adapters, SQS worker,
                    and the composition root (wiring.py). Depends on service.
```

Each package uses a `src/` layout with its own `pyproject.toml` and `tests/`.

### Key design rules (do not break these)

- **boto3 lives only in `rebridge_data`** (and `rebridge_api/wiring.py`, the
  composition root that constructs the concretes). The service layer must stay
  free of AWS and web-framework imports.
- **Program against interfaces.** Service classes receive data-layer
  collaborators via constructor injection (the abstract `ItemRepository`,
  `ObjectStore`, `CardSigner`, `GradingProvider`, etc. in
  `rebridge_data/interfaces.py`). Concrete wiring happens only in `wiring.py`.
- **The composition root is the single wiring point.** `wiring.py` builds all
  concretes once and injects them. Importing it makes no AWS calls (clients are
  created but not invoked).
- **Two separate Lambda entrypoints share one core:**
  - HTTP: `rebridge_api.http_adapter.handler` (Mangum-wrapped FastAPI).
  - SQS worker: `rebridge_api.worker.lambda_handler`.
  Both drive the same `GradingPipeline`, so sync/async parity is free.

## Core components

Service layer (`rebridge_service/src/rebridge_service/`):
- `item_service.py` — item create/get, presigned photo uploads, listing CRUD.
- `quality_precheck.py` — blur (variance-of-Laplacian) + exposure gating.
- `grading_engine.py` — provider cascade (Nova Lite -> Claude vision), per-call
  timeout, strict-JSON parse with retry, `TotalCascadeFailure`.
- `grade_schema.py` — canonical grade-assessment JSON schema + strict parser.
- `confidence_gate.py` — auto-continue vs review (default threshold 0.80).
- `idempotency.py` — deterministic key from item id + photo-set hash.
- `grading_pipeline.py` — orchestrates the whole grade flow with branching.
- `routing_agent.py` / `routing_tools.py` — disposition selection by margin;
  PriceEstimator (seeded CSV), CostModel, DemandProbe.
- `health_card_service.py` — render + HMAC sign + verify (recompute-and-compare).
- `demand_matching_engine.py` — candidate filter, weighted score, top-N push.
- `review_console_service.py` — review queue confirm/override + training signal.
- `eventing_service.py` — lifecycle event emission.

Data layer (`rebridge_data/src/rebridge_data/`):
- `interfaces.py` (ABCs) + `models.py` (persistence records).
- Concretes: `dynamo_item_repository.py`, `dynamo_review_queue_repository.py`,
  `s3_object_store.py`, `sqs_queue_client.py`, `kms_card_signer.py`,
  `eventbridge_publisher.py`, `bedrock_grading_providers.py`,
  `seeded_buyer_persona_repository.py`, `geohash.py`.
- Seed data (package data): `data/price_bands.csv`, `data/buyer_personas.json`.

API layer (`rebridge_api/src/rebridge_api/`):
- `app.py` — `create_app(services=None, extra_routers=None)` factory + `/healthz`.
- `routers/` — `items.py`, `listings.py`, `marketplace.py`, `cards.py`.
- `dependencies.py` — `Services` container, `get_services`, `get_current_user`.
- `auth.py` — `CognitoJwtVerifier` (RS256/JWKS).
- `http_adapter.py` — Mangum Lambda handler.
- `worker.py` — SQS worker with retry + DLQ partial-batch responses.
- `wiring.py` — `Settings`, `build_services`, `build_app`, `build_worker`.

## Running tests

A shared runner sits at the repo root:

```
python run_tests.py            # all three packages
python run_tests.py data       # one package: data | service | api
```

Each package runs its own pytest suite from its own directory. There are
**537 tests** today (118 data + 330 service + 89 api), all passing.

First-time setup (editable installs into the local venv):

```
python -m venv .venv
.venv\Scripts\activate            # Windows; use source .venv/bin/activate on *nix
pip install -e ./rebridge_data[test] -e ./rebridge_service[test] -e ./rebridge_api[test]
```

## Testing conventions

- **Property-based testing is central.** All 29 design correctness properties
  have a dedicated Hypothesis test (>=100 iterations each), tagged exactly:
  `# Feature: rebridge-backend, Property <N>: <text>`. Keep that tag if you
  touch them. Property tests live next to the code they validate (service or
  api `tests/`).
- **Tests use in-memory fakes, not mocks.** Service tests run against the fakes
  in `rebridge_service/tests/fakes.py` (and `rebridge_api/tests/fakes.py`).
  The programmable `FakeGradingProvider` scripts cascade/timeout/bad-JSON cases.
- **Data-layer tests use moto** (`mock_aws`) for DynamoDB/S3/SQS/EventBridge.
  KMS `GenerateMac` is unit-tested with an injected fake/stub (moto's MAC isn't
  a stable HMAC); real KMS is only exercised at deployment.
- **Injectable clocks/ids/sleep/jitter** keep tests deterministic and fast — no
  real wall-clock sleeps, no real time in the worker backoff tests.
- After any change, run the relevant package suite (or all) before declaring done.

## Configuration

All runtime config is read from `REBRIDGE_*` environment variables by
`Settings.from_env()`. See `.env.example` for the full list. Defaults make the
app constructible offline; AWS resource ids must be set for deployment.

## Gotchas / things to know

- The HTTP Lambda handler is `http_adapter.py` (NOT `lambda_handler.py`) to
  avoid colliding with the worker's `lambda_handler` function name.
- Money is `Decimal` end to end (price/value/cost/margin) — don't introduce
  float math into routing/pricing.
- Location is stored only as **Geohash5** (~5 km) — never persist finer.
- `put_grade_if_absent` is the idempotency seam: a DynamoDB conditional write;
  re-processing the same submission is a safe no-op.
- The `buy` endpoint is a **simulated** checkout (emits SOLD, no payment). v1 has
  no payment gateway, no fraud ML, and no donation logistics — `test_scope_boundary.py`
  enforces these absences. Don't add those concerns without updating scope.
- The seeded buyer-persona repository is the **only** demand source in v1.
- Seed CSV/JSON values are synthetic placeholders; tune before production.

## Spec

The authoritative spec lives in `.kiro/specs/rebridge-backend/`
(`requirements.md`, `design.md`, `tasks.md`). The design's Correctness
Properties section is the source of truth for the property tests.

---

## What was added / fixed after the initial implementation

### Frontend (`frontend/`)
A full Next.js 14 / TypeScript / Tailwind frontend (App Router) was delivered and lives at the repo root. It has its own `package.json`, `tsconfig.json`, Playwright e2e suite, and `.env.example`. Run with:
```bash
cd frontend && npm run dev   # http://localhost:3000
```
All routes default to **mock** services. Flip individual `NEXT_PUBLIC_*_LIVE` env flags in `frontend/.env.local` to point at the live backend (see `documentation/FOR_BACKEND.md`).

Key frontend routes: `/returns` (capture + grade), `/reveal` (grading reveal), `/scanner` (3D product scanner), `/market` (buyer marketplace), `/card/[id]` (Health Card verify), `/notifications`, `/review` (review console), `/` (hero), `/styleguide`.

### G1–G4 backend endpoints (added)
The frontend contract specified four endpoints the original backend didn't expose:

| Endpoint | Purpose |
|---|---|
| `GET /items/{id}/matches` | Ranked buyer matches for a graded item (Engine B read view) |
| `GET /review/queue` | Prioritized review queue with server-computed priority tiers |
| `POST /review/{item_id}` | Confirm or override a pending grade |
| `GET /marketplace` (extended) | Now also returns `grade`, `distance_km`, `price_new`, `health_card_id`, `title`, `thumb_key`, `listing_id` per listing; accepts `category=all` |

New routers: `routers/matches.py`, `routers/review.py`. `routers/marketplace.py` extended. See `openapi.json` at the repo root for the full machine-readable contract.

### Four runtime connection fixes
These services were fully implemented and tested in isolation but never connected to the runtime:

**Fix 1 — Engine B end-to-end (the main one)**
`DemandMatchingEngine.match()` (notify buyers + shelf + `MATCHED` event) was never called.
- Added `rebridge_data/eventbridge_demand_gateways.py`: `EventBridgeBuyerNotifier` and `EventBridgeSecondChanceShelf` — both publish events on the existing EventBridge bus (`BUYER_NOTIFIED` per buyer, `SHELF_UPSERTED` per item). No new infrastructure.
- Wired into `wiring.py` — demand engine now receives `notifier`, `shelf`, `eventing`.
- `match()` is now triggered in `routers/listings.py` on listing creation (the design-specified trigger point).

**Fix 2 — `ROUTED` on the async grading path**
The worker's pipeline called `RoutingAgent.decide()` directly; the agent persists the decision but doesn't emit. `ROUTED` was only emitted on the explicit `POST /items/{id}/route` endpoint.
- Added `rebridge_api/routing_adapter.py`: `EventEmittingRouter` wraps the agent, calls `decide()` then `emit_routed()`.
- `wiring.py` `build_worker` now uses `EventEmittingRouter` instead of `CallableRouter`.

**Fix 3 — `GRADED` after human review**
`ReviewConsoleService.confirm/override` set status `GRADED` but never emitted the `GRADED` event.
- `routers/review.py` now calls `services.eventing.emit_graded(item_id)` after the action.

**Fix 4 — Composition-level regression tests**
Added `rebridge_api/tests/test_event_wiring.py` (4 tests) and `test_routing_adapter.py` — these run through the composed harness so "implemented but never connected" can't silently pass a green suite again.

### Test counts after all changes
| Package | Tests |
|---|---|
| `rebridge_data` | 134 |
| `rebridge_service` | 342 |
| `rebridge_api` | 110 |
| **Total** | **586** |
