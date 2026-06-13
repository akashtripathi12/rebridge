# ReBridge Backend

AI-assisted returns-grading and routing backend. A returned item is photographed,
graded by a vision-model cascade, issued a signed tamper-evident **Product Health
Card**, routed to the best disposition by unit economics (resell / refurb /
peer-to-peer / donate), and matched to likely buyers. Low-confidence grades are
sent to a human review queue.

## Architecture

A Python monorepo of three independently-installable packages with a strict
one-way dependency `api → service → data`:

| Package | Role | Notes |
| --- | --- | --- |
| `rebridge_data` | Abstract interfaces + boto3-backed concretes (DynamoDB, S3, SQS, KMS, EventBridge, Bedrock) | The **only** package that imports `boto3` |
| `rebridge_service` | Pure business logic (grading pipeline, routing, health cards, demand matching, review, eventing) | Framework-free; no `boto3`, no web framework |
| `rebridge_api` | FastAPI routers, Cognito JWT auth, Lambda adapters, SQS worker, composition root | Depends on `rebridge_service` |

Each package uses a `src/` layout (`<pkg>/src/<pkg>/`) with its own
`pyproject.toml` and `tests/`. See [`CLAUDE.md`](CLAUDE.md) for the full
architecture guide and conventions.

## Quick start

```bash
# create and activate a virtualenv
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux

# editable-install all three packages with test extras
pip install -e ./rebridge_data[test] -e ./rebridge_service[test] -e ./rebridge_api[test]

# run the tests
python run_tests.py               # all packages
python run_tests.py service       # one package: data | service | api
```

## Configuration

Runtime configuration is read from `REBRIDGE_*` environment variables by the
composition root (`rebridge_api/.../wiring.py`). Copy
[`.env.example`](.env.example) to `.env` and fill in real values for a
deployment. Defaults make the app constructible offline.

```python
from rebridge_api.wiring import Settings, build_app
app = build_app(Settings.from_env())   # no AWS calls at construction time
```

## Entrypoints

- **HTTP (API Gateway → Lambda):** `rebridge_api.http_adapter.handler` (Mangum-wrapped FastAPI)
- **Async grading (SQS → Lambda):** `rebridge_api.worker.lambda_handler`

Both drive the same `GradingPipeline`, so sync/async behavior stays identical.

## Testing

- **537 tests** across the three packages (data + service + api), all passing.
- All 29 design correctness properties have dedicated [Hypothesis](https://hypothesis.readthedocs.io/)
  property tests (≥100 iterations each).
- Service tests use in-memory fakes; data-layer tests use [`moto`](https://github.com/getmoto/moto) for mocked AWS.

## v1 scope boundaries

Intentionally **not** in v1 (enforced by `tests/test_scope_boundary.py`):

- No live payments — `POST /listings/{id}/buy` is a simulated checkout that emits `SOLD`.
- No fraud-detection ML.
- No donation-logistics execution.
- Seeded buyer personas are the only demand source.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture, conventions, and gotchas.
- [`documentation/`](documentation/) — product, business, architecture, and
  implementation documents, plus the project handoff (`HANDOFF.md`).
- `.kiro/specs/rebridge-backend/` — the authoritative requirements, design, and tasks spec.

## License

Released under the [MIT License](LICENSE).
