# ReBridge Backend — Handoff

Status as of handoff: **all 90 spec tasks complete, 537 tests passing**
(118 data + 330 service + 89 api). Exit code 0 on `python run_tests.py`.

This document is the practical "where things stand and what's next" companion to
`CLAUDE.md` (architecture/conventions) and the spec in
`.kiro/specs/rebridge-backend/`.

---

## 1. What was delivered

A complete, tested v1 implementation of the ReBridge returns-grading backend as a
three-package Python monorepo (`rebridge_data` -> `rebridge_service` ->
`rebridge_api`). Every component described in `design.md` is implemented and
unit/property/integration tested against in-memory fakes and moto-mocked AWS.

Functional slices delivered end to end:
- Item lifecycle: create (order-scan / manual), presigned photo upload, aggregate retrieval.
- Quality precheck (blur + exposure) gating before grading.
- Grading: Bedrock cascade (Nova Lite -> Claude vision), strict-JSON parse + retry, timeout fallthrough.
- Confidence gate (default 0.80) -> auto-continue or human review.
- Idempotent grading pipeline (S3 -> SQS -> worker), retry + DLQ.
- Product Health Card: render, HMAC-sign (KMS), persist, public QR verify.
- Routing agent: margin-based disposition selection + persisted rationale.
- Demand matching: filter/score/rank seeded buyers, top-N push, Second-Chance shelf, MATCHED event.
- Review console: prioritized queue, confirm/override with training signal.
- Lifecycle eventing: GRADED, ROUTED, LISTED, MATCHED, SOLD via EventBridge.
- API: FastAPI routes, Cognito JWT on private routes, public card-verify, Lambda HTTP adapter, SQS worker.
- Composition root (`wiring.py`) reading all config from `REBRIDGE_*` env vars.

All 29 correctness properties from the design have dedicated Hypothesis tests.

---

## 2. How to run it locally

```
# from d:\Amazon
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on *nix)
pip install -e ./rebridge_data[test] -e ./rebridge_service[test] -e ./rebridge_api[test]

python run_tests.py             # all suites; or: python run_tests.py data|service|api
```

To construct the app offline (no AWS calls happen at construction time):

```python
from rebridge_api.wiring import Settings, build_app
app = build_app(Settings.from_env())   # FastAPI app; clients built, not invoked
```

Copy `.env.example` to `.env` and fill in real resource ids before deploying.

---

## 3. Decisions & deviations worth knowing

- **HTTP Lambda handler is `rebridge_api.http_adapter.handler`**, not
  `lambda_handler.py` — that name would collide with the SQS worker's
  `lambda_handler` function (exported from the package). The worker entrypoint
  is `rebridge_api.worker.lambda_handler`.
- **KMS card signing is unit-tested with an injected fake/stub**, because moto's
  `GenerateMac`/`VerifyMac` does not return a stable, verifiable HMAC. The real
  KMS sign/verify is exercised only against a live key (deployment / manual smoke).
- **`ItemMeta` gained an optional `context_ref` field** (backward-compatible) to
  persist the scanned order reference for order-scan items.
- **Routing modeled in pure Python.** The design mentions LangGraph for the
  agent strategy; `AgentRoutingStrategy` walks the same gather→evaluate→select
  steps but delegates the final decision to the shared pure core, so agent and
  pure-function strategies are provably equivalent (Property 18). LangGraph is
  not a dependency.
- **Seed data is synthetic placeholder data** (authorized during the build):
  - `rebridge_data/.../data/price_bands.csv` — 6 categories × 5 grades × 4 age
    buckets, generated from a documented reference-price × grade × age-decay model.
  - `rebridge_data/.../data/buyer_personas.json` — 30 personas across 6 geohash5
    neighborhoods and 5 categories, including deal_seeker / price_balker types.
  Both are overridable via constructor injection.
- **Scoring/threshold constants are documented defaults**, not derived from the
  spec where the spec left them open: demand-match weights
  (intent 0.40, lifecycle/geo/price 0.20 each, anti-cannibalization bonus 0.15),
  precheck thresholds (blur variance 100.0, brightness band 40–220), per-route
  handling costs. Revisit these with real data.

---

## 4. What is NOT in v1 (intentional scope boundaries)

Enforced by `rebridge_api/tests/test_scope_boundary.py`:
- **No live payments** — `POST /listings/{id}/buy` is a simulated checkout that
  emits SOLD; there is no payment gateway.
- **No fraud-detection ML** — Pillar 5 prevention is data-capture shape only.
- **No donation logistics execution** — `DONATE` is a routing decision only.
- **Seeded personas are the only demand source.**

Don't add these without updating the spec and the scope-boundary tests.

---

## 5. Before production — required follow-ups

These are deployment/ops concerns the code is ready for but that live outside the
test suite:

1. **Infrastructure-as-code / provisioning** (not in this repo): DynamoDB table
   with GSI1 (marketplace), GSI2 (geo), GSI3 (review queue); S3 photo bucket with
   the S3->SQS event notification; SQS grading queue + DLQ with a RedrivePolicy
   (`maxReceiveCount` ~3) and a CloudWatch alarm on DLQ depth; KMS HMAC key;
   EventBridge bus; Cognito user pool + app client; two Lambda functions (HTTP +
   worker) with `ReportBatchItemFailures` enabled on the worker's event source.
2. **Set all `REBRIDGE_*` env vars** (see `.env.example`) and grant the Lambda
   IAM role least-privilege access to those resources + Bedrock model invoke.
3. **Wire the S3 upload-completion -> SQS enqueue glue.** The worker/SQS path is
   real and tested; the S3 ObjectCreated notification that constructs and enqueues
   the `GradingMessage` is represented in tests but the actual notification
   binding is infra config to finish.
4. **Bedrock model access** — confirm the Nova Lite and Claude vision model ids
   are enabled in your account/region; override via `REBRIDGE_*_MODEL_ID` if not.
5. **Tune seed data and constants** (section 3) against real catalog/pricing/demand data.
6. **Real end-to-end latency check** — the p99 test (`test_grading_latency_p99.py`)
   measures the mocked orchestration path (~1 ms); validate the real p99 including
   model inference against the 4 s budget (Requirement 9.1) in a staging env.

---

## 6. Where to look

- Architecture, conventions, gotchas: `CLAUDE.md`
- Config keys: `.env.example` + `rebridge_api/.../wiring.py`
- Spec (authoritative): `.kiro/specs/rebridge-backend/{requirements,design,tasks}.md`
- Correctness properties: design.md "Correctness Properties" section, mapped 1:1
  to the `test_*_property.py` files.

---

## Update — Frontend, G1–G4 endpoints, and four runtime-connection fixes

### What changed since the initial push

**Test count is now 586** (was 537). All pass.

---

### Frontend at `frontend/`
A complete Next.js 14 / TypeScript / Tailwind frontend (App Router) is now at the repo root. It was built against the backend contract in `documentation/CONTRACT_ADDENDUM.md` and all four nights of work (Phases 1–7) are complete with 33 Playwright gates passing (11 intentional desktop-only skips).

```bash
cd frontend && npm run dev     # http://localhost:3000
```

All services default to **mock** mode. Flip live per the table in `documentation/FOR_BACKEND.md` (copy `frontend/.env.example` to `frontend/.env.local`):

| Flag | Endpoint it switches | Screens it unblocks |
|---|---|---|
| `NEXT_PUBLIC_ITEMS_LIVE=true` | items / presign / grade / poll / route / listings / cards verify | Returns Desk, Reveal, Health Card |
| `NEXT_PUBLIC_MATCHING_LIVE=true` | `GET /items/{id}/matches` (G1) | "N buyers < 5 km" in Reveal; match push (Phase 5) |
| `NEXT_PUBLIC_REVIEW_LIVE=true` | `GET /review/queue`, `POST /review/{id}` (G2) | Review console (Phase 6) |
| `NEXT_PUBLIC_MARKETPLACE_LIVE=true` | `GET /marketplace` extended (G3/G4) | Buyer marketplace (Phase 5) |
| Cognito env vars | real JWT auth | all private routes |

---

### New backend endpoints (G1–G4)

| Endpoint | Notes |
|---|---|
| `GET /items/{id}/matches` | Ranked buyers, `distance_km`, `match_score`, `intent_tier`, `match_count_within_5km`, `top_reason`. Empty when ungraded. |
| `GET /review/queue` | Sorted by priority (value × uncertainty). `priority` tier: HIGH≥300, MEDIUM≥50, LOW otherwise. |
| `POST /review/{item_id}` | `{"action":"CONFIRM"/"OVERRIDE","override_grade":null/"<Grade>"}` → returns updated `ItemAggregate` with `meta.status = GRADED`. |
| `GET /marketplace?category&geo&limit` | Extended: each listing now carries `grade`, `distance_km`, `price_new`, `health_card_id`, `title`, `thumb_key`, `listing_id`. `category=all` accepted. |

Full contract: `openapi.json` at the repo root.

---

### Four runtime-connection fixes

These were "implemented but never wired" — all prior tests passed because each piece was tested in isolation, but the composed runtime never triggered them.

**Fix 1 — Engine B end-to-end (the critical one)**
`DemandMatchingEngine.match()` was never called at runtime. The two seams it needs (`BuyerNotifier`, `SecondChanceShelf`) had no concrete implementations.
- New: `rebridge_data/eventbridge_demand_gateways.py` — `EventBridgeBuyerNotifier` and `EventBridgeSecondChanceShelf` publish `BUYER_NOTIFIED` / `SHELF_UPSERTED` events on the existing EventBridge bus. No new infrastructure.
- `wiring.py` injects `notifier`, `shelf`, and `eventing` into the demand engine.
- `routers/listings.py` calls `matching.match()` on listing creation (the correct trigger point).

**Fix 2 — `ROUTED` on the async grading path**
The SQS worker's pipeline used `CallableRouter(routing.decide)` — the agent persists the decision but never emitted `ROUTED`. The event only fired on the explicit `POST /items/{id}/route` endpoint.
- New: `rebridge_api/routing_adapter.py` — `EventEmittingRouter` calls `decide()` then `emit_routed()`.
- `wiring.py` `build_worker` now uses `EventEmittingRouter` instead of `CallableRouter`.

**Fix 3 — `GRADED` after human review**
`ReviewConsoleService.confirm/override` set `meta.status = GRADED` but never emitted the lifecycle event.
- `routers/review.py` now calls `services.eventing.emit_graded(item_id)` after the action.

**Fix 4 — Composition-level regression tests**
- `rebridge_api/tests/test_event_wiring.py` — verifies listing creation triggers MATCHED + buyer notifications + shelf, and review confirm/override emits GRADED, through the fully composed harness.
- `rebridge_api/tests/test_routing_adapter.py` — verifies `EventEmittingRouter` emits ROUTED with the correct disposition.

---

### Pre-production additions (on top of the original §5 checklist)

- **EventBridge rule bindings** — create rules on the `rebridge-lifecycle` bus for the two new detail-types: `BUYER_NOTIFIED` (fan-out to push/email Lambda) and `SHELF_UPSERTED` (Second-Chance PDP shelf rebuild Lambda). Events fire today; consumers are the deployment step.
- **Frontend Cognito setup** — set `NEXT_PUBLIC_COGNITO_REGION`, `NEXT_PUBLIC_COGNITO_USER_POOL_ID`, `NEXT_PUBLIC_COGNITO_APP_CLIENT_ID`, and `NEXT_PUBLIC_API_BASE_URL` in the frontend's production env. Dev mock token keeps all screens functional until then.
- **Frontend deployment** — Next.js 14 App Router; deploy to Vercel, Amplify Hosting, or any Node-compatible host. Build: `cd frontend && npm run build`.
