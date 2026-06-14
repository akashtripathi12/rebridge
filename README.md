# ReBridge

AI-powered returns-grading, routing, and buyer-matching platform. A returned item
is photographed, graded by a vision-model cascade, issued a signed tamper-evident
**Product Health Card**, routed to the best disposition by unit economics
(resell / refurb / peer-to-peer / donate), and matched to nearby buyers.
Low-confidence grades go to a human review queue. A full Next.js buyer/seller
frontend ships alongside the backend.

---

## Repo layout

```
rebridge/
├── frontend/              Next.js 14 App Router (TypeScript + Tailwind)
├── rebridge_data/         Python: interfaces + boto3-backed concretes
├── rebridge_service/      Python: pure business logic (no boto3, no framework)
├── rebridge_api/          Python: FastAPI, Lambda adapters, SQS worker, composition root
├── documentation/         Product, architecture, contract, and handoff docs
├── openapi.json           Live OpenAPI contract (all 16 endpoints)
├── CLAUDE.md              Architecture guide, conventions, and gotchas
├── .env.example           Backend env-var reference
└── run_tests.py           Runs all three Python package suites
```

---

## Backend

### Architecture — 3-package monorepo, one-way dependency

```
rebridge_api  →  rebridge_service  →  rebridge_data
```

| Package | Role | AWS / framework? |
|---|---|---|
| `rebridge_data` | Abstract interfaces + boto3 concretes (DynamoDB, S3, SQS, KMS, EventBridge, Bedrock) | **boto3 only here** |
| `rebridge_service` | Pure business logic — grading pipeline, routing agent, health cards, demand matching, review console, eventing | **None** |
| `rebridge_api` | FastAPI routers, Cognito JWT auth, Mangum Lambda adapter, SQS worker, composition root (`wiring.py`) | FastAPI + Mangum |

Each package uses a `src/` layout with its own `pyproject.toml` and `tests/`.

### Quick start (backend)

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows — use source .venv/bin/activate on macOS/Linux
pip install -e ./rebridge_data[test] -e ./rebridge_service[test] -e ./rebridge_api[test]

python run_tests.py              # all 3 packages  (586 tests, all green)
python run_tests.py service      # one package: data | service | api
```

### Configuration

All runtime config is read from `REBRIDGE_*` environment variables. Copy
[`.env.example`](.env.example) to `.env` and fill in real values. Defaults make
the app constructible offline (no AWS calls at import time).

```python
from rebridge_api.wiring import Settings, build_app
app = build_app(Settings.from_env())
```

### Lambda entrypoints

| Entrypoint | Purpose |
|---|---|
| `rebridge_api.http_adapter.handler` | Mangum-wrapped FastAPI behind API Gateway |
| `rebridge_api.worker.lambda_handler` | SQS-triggered async grading worker |

Both drive the same `GradingPipeline` — sync/async behavior is identical.

### API endpoints (16 total)

Full contract: [`openapi.json`](openapi.json). All private routes require
`Authorization: Bearer <Cognito JWT>`.

| Method | Path | Notes |
|---|---|---|
| GET | `/healthz` | Public liveness probe |
| POST | `/items` | Create item (order-scan or manual) |
| POST | `/items/{id}/photos:presign` | S3 presigned PUT URLs (2–4 photos) |
| POST | `/items/{id}/grade` | Enqueue async grading → 202 |
| GET | `/items/{id}` | Aggregate: meta + grade + card + decision + listing |
| GET | `/items/{id}/matches` | Ranked buyer matches (demand engine) |
| POST | `/items/{id}/route` | Run/persist routing decision |
| POST | `/listings` | Create listing (requires graded item) |
| GET | `/listings/{id}` | Get listing |
| PUT | `/listings/{id}` | Partial update |
| DELETE | `/listings/{id}` | Remove listing |
| POST | `/listings/{id}/buy` | Simulated checkout → SOLD |
| GET | `/marketplace` | Browse listings (grade / distance / price_new / `category=all` supported) |
| GET | `/cards/{id}/verify` | Public QR health-card verification |
| GET | `/review/queue` | Prioritized human-review queue |
| POST | `/review/{id}` | Confirm or override a pending grade |

### Testing — 586 tests, 0 failures

- All 29 design correctness properties have [Hypothesis](https://hypothesis.readthedocs.io/)
  property tests (≥100 iterations each).
- Service-layer tests use in-memory fakes (no AWS). Data-layer tests use
  [moto](https://github.com/getmoto/moto). Composition-level tests verify
  end-to-end event wiring across connected services.

---

## Frontend

A complete **Next.js 14** (App Router) + TypeScript + Tailwind frontend with
33 Playwright e2e gates (11 intentional desktop-only skips).

### Quick start (frontend)

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

All services default to **mock** mode. To connect to the live backend, copy
`frontend/.env.example` to `frontend/.env.local` and flip:

| Flag | Endpoint | Screens |
|---|---|---|
| `NEXT_PUBLIC_ITEMS_LIVE=true` | items / presign / grade / route / listings / cards | Returns Desk, Reveal, Health Card |
| `NEXT_PUBLIC_MATCHING_LIVE=true` | `GET /items/{id}/matches` | "N buyers" in Reveal, match push |
| `NEXT_PUBLIC_REVIEW_LIVE=true` | `GET /review/queue` + `POST /review/{id}` | Review console |
| `NEXT_PUBLIC_MARKETPLACE_LIVE=true` | `GET /marketplace` | Buyer marketplace |
| Cognito env vars | JWT auth | All private routes |

### Frontend routes

| Route | Description |
|---|---|
| `/` | Hero — animated product journey |
| `/returns` | Returns Desk — photo capture + async grade round-trip |
| `/reveal` | Grading Reveal — theatre paced over the real grade poll |
| `/scanner` | 3D Product Scanner — r3f + WebGL2, defect hotspots |
| `/market` | Buyer Marketplace — match push + proactive card |
| `/card/[id]` | Product Health Card — verifiable trust artifact with real QR |
| `/notifications` | Seller + buyer routing notifications |
| `/review` | Human Review Console — confirm / override low-confidence grades |
| `/styleguide` | Component reference |

---

## v1 scope boundaries

Enforced by `rebridge_api/tests/test_scope_boundary.py`:

- **No live payments** — `POST /listings/{id}/buy` emits `SOLD`; no payment gateway.
- **No fraud-detection ML.**
- **No donation-logistics execution** — `DONATE` is a routing decision only.
- **Seeded buyer personas are the only demand source.**

---

## Documentation

| File | Contents |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Architecture, component map, conventions, gotchas |
| [`documentation/HANDOFF.md`](documentation/HANDOFF.md) | End-to-end handoff, pre-production checklist |
| [`documentation/CONTRACT_ADDENDUM.md`](documentation/CONTRACT_ADDENDUM.md) | Agreed frontend↔backend API contract (gaps G1–G9) |
| [`documentation/BACKEND_MAP.md`](documentation/BACKEND_MAP.md) | Full backend contract map (wire shapes, enums, status machine) |
| [`documentation/FOR_BACKEND.md`](documentation/FOR_BACKEND.md) | Sunrise checklist — exact endpoint shapes the frontend expects |
| [`documentation/PROGRESS.md`](documentation/PROGRESS.md) | Frontend build progress (Phases 1–7, all green) |
| [`documentation/DEMO_SCRIPT.md`](documentation/DEMO_SCRIPT.md) | Scripted demo path |
| [`.kiro/specs/rebridge-backend/`](.kiro/specs/rebridge-backend/) | Authoritative requirements, design, and tasks spec |

---

## License

Released under the [MIT License](LICENSE).
