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
