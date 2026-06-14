# BACKEND_MAP.md — ReBridge Backend Contract (Phase 0)

> **Source of truth.** Everything below was read from the actual backend code in
> this repo and verified by (a) generating the live OpenAPI spec from the wired
> app (`openapi.json`, committed alongside this file) and (b) running real
> request round-trips through the app wired to the in-memory test fakes. Field
> names, enum values, status codes, and serialization formats are copied from
> code, not assumed.
>
> **Verification method:** the boto3-wired app constructs offline but real
> requests need live AWS (DynamoDB/S3/SQS/KMS). To capture exact wire shapes I
> built the app with the repo's own test fakes (`rebridge_api/tests/fakes.py`)
> and exercised every route. `/healthz` also serves on the fully-wired app.

---

## 1. Architecture — the 3 layers (named as the code names them)

A Python monorepo, strict one-way dependency **`api → service → data`**. Never
import "up" that chain.

| Layer (package) | Responsibility (one line) | AWS? Framework? |
|---|---|---|
| **`rebridge_api`** | FastAPI routers, Cognito JWT auth, Lambda HTTP adapter + SQS worker, and the composition root (`wiring.py`) that builds & injects everything. | FastAPI + Mangum; boto3 **only** in `wiring.py`. |
| **`rebridge_service`** | Pure business logic — grading pipeline, routing agent, health cards, demand matching, review console, eventing. Programmed against `rebridge_data` interfaces. | **No** boto3, **no** web framework. |
| **`rebridge_data`** | Abstract interfaces (ABCs) + boto3-backed concretes (DynamoDB, S3, SQS, KMS, EventBridge, Bedrock) + persistence records + seed data. | The **only** package allowed to import boto3. |

**Where the two AI engines live (service layer):**
- **Engine A — grading:** `grading_pipeline.py` orchestrates `quality_precheck` →
  `grading_engine` (Bedrock **Nova Lite → Claude vision** cascade) →
  `confidence_gate` → grade/card/route **or** review queue.
- **Engine B — matching:** `demand_matching_engine.py` (filter → weighted score →
  rank → top-N push). ⚠️ **Built and wired but NOT exposed over HTTP** — see Gaps.
- **Routing** (`routing_agent.py`) is a separate unit-economics decision engine,
  exposed at `POST /items/{id}/route`.

**Composition root:** `rebridge_api/src/rebridge_api/wiring.py` —
`Settings.from_env()` → `build_services()` / `build_app()` / `build_worker()`.
Two Lambda entrypoints share one core: HTTP `http_adapter.handler` (Mangum) and
SQS worker `worker.lambda_handler`.

---

## 2. Auth flow (what the frontend must send)

- **Scheme:** OAuth2 / **Cognito-issued JWT**, sent as
  **`Authorization: Bearer <token>`**. (`dependencies.py::get_current_user`.)
- **Token validation (server side):** RS256 signature against the user pool's
  JWKS, `iss` = `https://cognito-idp.{region}.amazonaws.com/{userPoolId}`, `exp`,
  and app-client id matched against **`aud`** (id-tokens) **or** `client_id`
  (access-tokens). Either an id-token or access-token works as long as the client
  id matches. (`auth.py::CognitoJwtVerifier`.)
- **Missing / malformed / expired / wrong-issuer / wrong-audience → `401`** with
  `WWW-Authenticate: Bearer`.
- ⚠️ **There is NO login / token / signup / refresh endpoint in this backend.**
  The frontend must obtain the JWT directly from **Amazon Cognito** itself
  (Hosted UI redirect, or Amplify Auth / SRP against the user pool). The backend
  only *verifies* tokens. → **Open question #1.**
- **Public (no-auth) routes:** `GET /healthz` and `GET /cards/{card_id}/verify`
  (the QR target). Everything else requires the bearer token.

---

## 3. Async grading model (decides how the UI waits)

**Grading is ASYNCHRONOUS. Confirm: yes — fire-and-forget + poll.**

1. `POST /items/{id}/grade` → **`202 Accepted`** immediately with an
   `idempotency_key` (also echoed in the **`Idempotency-Key`** response header).
   It only **enqueues** an SQS `GradingMessage`; **no grade is in this response.**
2. The SQS **worker** (`worker.lambda_handler` → `GradingPipeline.run`) processes
   it: idempotency check → fetch photos from S3 → quality precheck → model
   cascade → confidence gate → branch.
3. **The frontend learns the result by polling `GET /items/{id}`** and reading
   `meta.status` (and once present, the `grade` / `card` / `decision` facets).
   ⚠️ **There is no dedicated job-status endpoint, no webhook, no websocket, and
   no SSE.** Poll `GET /items/{id}` until status leaves `GRADING`.

**Status machine (`meta.status`, drives the poll):**

```
CREATED ──grade enqueued──▶ GRADING ──┬─▶ GRADED          (confidence ≥ threshold; grade+card+decision written)
                                       ├─▶ PENDING_REVIEW  (confidence < threshold, OR model failure)
                                       └─▶ RETAKE_REQUIRED (blur/exposure precheck failed)
GRADED ──create listing──▶ LISTED ──buy──▶ SOLD
```

- **Confidence threshold default = `0.80`** (`REBRIDGE_CONFIDENCE_THRESHOLD`).
  `confidence ≥ 0.80` auto-continues; below → human review.
- **Idempotency:** key is derived deterministically from `item_id` + photo-set
  hash unless the client supplies `idempotency_key`. Re-submitting the same set
  is a safe no-op.
- For the demo: the same `GradingPipeline` can run synchronously (the worker and
  HTTP paths are identical), but **the shipped HTTP API only enqueues** — there
  is no sync grade endpoint. → see Gaps / Open question #2.

---

## 4. Enums — verbatim from code

**`Grade`** (`rebridge_service/models.py::Grade`, wire = the string value):
```
"Like New" · "Very Good" · "Good" · "Acceptable" · "Unsellable"
```
**`Disposition`** (routing decision, `rebridge_service/models.py::Disposition`):
```
"RESELL" · "REFURB" · "P2P" · "DONATE"
```
**`ItemStatus`** (`meta.status`):
```
"CREATED" · "RETAKE_REQUIRED" · "GRADING" · "PENDING_REVIEW" · "GRADED" · "LISTED" · "SOLD"
```
**`EventType`** (internal lifecycle events; not directly returned to the FE):
```
"GRADED" · "ROUTED" · "LISTED" · "MATCHED" · "SOLD"
```
**Listing status** — free string; service default on create = **`"ACTIVE"`**.
**`context_source`** (item create) — **`"order_scan"`** or **`"manual"`**.
**Warranty stance** (rendered on the card, by grade) — `"30-day returns"`
(Like New / Very Good), `"14-day returns"` (Good), `"7-day returns"`
(Acceptable), `"no warranty (not resellable)"` (Unsellable).
**Seeded buyer `persona_type`:** `deal_seeker`, `price_balker` (these two get the
anti-cannibalization bonus), `browser`, `collector`, `gifter`.
**Defect `severity` / `location`:** **free-text strings**, not enums or
coordinates (e.g. `location:"toe cap"`, `severity:"minor"`).

**Money serialization (important):** all money (`price`, `value`, `cost`,
`margin`) is `Decimal` end-to-end and serializes to JSON as a **string**, e.g.
`"340.00"`, `"36.00"`. The frontend must parse strings → number for display
(and keep them mono per the design). **`confidence` is a JSON number** in `[0,1]`.

---

## 5. Full endpoint inventory

13 routes (verified against generated `openapi.json`). All require
`Authorization: Bearer` **except** `/healthz` and `/cards/{id}/verify`.

Common error envelope: `{ "detail": string, "field"?: string }`.
Error status map (`errors.py`): `404` unknown item/listing/card · `422`
missing/invalid field or bad photo count (with `field`) · `409` grade-required
or review-on-non-pending · `401` auth.

---

### 5.1 `GET /healthz` — liveness (public)
→ `200 {"status":"ok"}`

---

### 5.2 `POST /items` — create item · auth · `201`
**Body** (`CreateItemRequest`, `extra:"allow"`):
```jsonc
{ "context_source": "order_scan" | "manual",   // required
  "category": "string",                          // required
  "age_months": 6,                               // required (int)
  "order_id": "AMZ-123" }                        // required IFF context_source=="order_scan"
```
**`201` →** (`ItemMetaResponse`)
```json
{ "item_id":"f95..","status":"CREATED","category":"sneakers","age_months":6,
  "context_source":"order_scan","created_at":"2026-06-13T21:20:06.134408+00:00",
  "context_ref":"AMZ-123" }
```
Missing required field → `422 {"detail":"missing required field: category","field":"category"}`.
Bad `context_source` → `422` (`field:"context_source"`).

---

### 5.3 `POST /items/{item_id}/photos:presign` — get S3 upload URLs · auth · `200`
> Note the literal `:presign` in the path (`/items/{id}/photos:presign`).

**Body** (`PresignRequest`): `{ "count": 3 }` — must be **2–4 inclusive**.
**`200` →** (`PresignResponse`)
```json
{ "item_id":"f95..",
  "urls":[ {"url":"https://…s3…/items/f95../photo-1","method":"PUT","headers":{},"expires_in":300}, … ] }
```
- One presigned **PUT** URL per slot; **TTL 300s**; object keys are
  `items/{item_id}/photo-{1..count}`. **The browser PUTs the raw image bytes
  directly to `url`** (bytes never go through the API). `headers` is normally
  empty (no enforced Content-Type) — send the file as the PUT body.
- `count` outside 2–4 → `422 (field:"count")`; unknown item → `404`.

---

### 5.4 `POST /items/{item_id}/grade` — enqueue grading (async) · auth · `202`
**Body** (`GradeRequest`):
```jsonc
{ "photo_keys": ["items/f95../photo-1","items/f95../photo-2"],  // the uploaded S3 keys
  "idempotency_key": "optional-override" }
```
**`202` →** `{ "item_id":"f95..","idempotency_key":"<64-hex>","status":"enqueued" }`
plus response header **`Idempotency-Key: <same>`**. Unknown item → `404`.
**Then poll `GET /items/{id}`** (see §3).

---

### 5.5 `GET /items/{item_id}` — aggregate (the poll target) · auth · `200`
**`200` →** (`ItemAggregateResponse`) — `meta` always present; `grade`/`card`/
`decision`/`listing` are each `null` until they exist:
```jsonc
{
  "meta": { "item_id","status","category","age_months","context_source","created_at","context_ref" },
  "grade": {                                  // appears once graded / pending review
    "grade":"Good", "confidence":0.83, "summary":"Light scuffs on the toe.",
    "defects":[ {"location":"toe cap","severity":"minor"} ],
    "completeness": {"complete":true,"missing_components":[]},
    "idem_key":"k1", "confirmed":false        // confirmed=true after human review
  },
  "card": {                                   // appears once auto-graded (GRADED)
    "card_id","item_id","signature","qr_target",
    "graded_at","warranty_stance":"14-day returns","annotated_photo_keys":[…] },
  "decision": {                               // appears after grading auto-route OR POST /route
    "disposition":"P2P","price":"36.00","value":"36.00","cost":"5.50",
    "margin":"30.50","rationale":"P2P selected: highest-margin viable path (…)." },
  "listing": {                                // appears once listed
    "item_id","status":"ACTIVE","category","price":"340.00","geohash5":"tdr1y","listed_at" }
}
```
Unknown id → `404`.

---

### 5.6 `POST /items/{item_id}/route` — run/persist routing decision · auth · `200`
**Body** (`RouteRequest`, optional): `{ "geohash5": "tdr1y" }` (only enriches the
rationale; never changes the margin-based pick). **`200` →** (`RouteDecisionResponse`)
```json
{ "disposition":"P2P","price":"36.00","value":"36.00","cost":"5.50","margin":"30.50",
  "rationale":"P2P selected: highest-margin viable path (recovered value $36.00, handling cost $5.50, margin $30.50)." }
```
Unknown item → `404`; **ungraded item → `409`** (grade required). Note: a
`decision` facet is **also produced automatically** by the grading pipeline on
auto-grade, so it may already be present in `GET /items/{id}` without calling this.

> ⚠️ `decision.price` is the **recoverable price band point** (what ReBridge
> expects to recover, e.g. `$36`), **not** the listing/retail price. The listing
> `price` (e.g. `$340`) is what the operator sets at `POST /listings`. There is
> **no "original / new" price field** anywhere (see Gaps — needed for the card's
> "price vs new").

---

### 5.7 Listings — `POST /listings` (`201`) · `GET/PUT/DELETE /listings/{item_id}` · `POST /listings/{item_id}/buy`
**Create** (`CreateListingRequest`): `{ "item_id","category","price":"340.00","geohash5","status"? }`
→ `201` (`ListingResponse` = the LISTING facet). Requires the item to be **graded**
(ungraded → `409`); transitions item to `LISTED` and emits `LISTED`.
**Get/Update/Delete** keyed by **`item_id`** (the LISTING facet is keyed to its
item). `PUT` is a partial patch (`status/category/price/geohash5`). `DELETE` → `204`.
**Buy** `POST /listings/{item_id}/buy` → `200`:
```json
{ "item_id":"f95..","status":"SOLD","order_id":"<hex>","simulated":true,
  "message":"Simulated checkout: no payment processed. SOLD event emitted." }
```
**Simulated only — no payment.** Transitions to `SOLD`, emits `SOLD`.

---

### 5.8 `GET /marketplace` — browse listings · auth · `200`
**Query:** `category` (**required**), `geo` (optional geohash prefix),
`limit` (1–200, default 50). **`200` →**
```json
{ "listings":[ {"item_id","status","category","price":"340.00","geohash5":"tdr1y","listed_at"} , … ] }
```
⚠️ Each listing carries **only** item_id/status/category/price/geohash5/listed_at —
**no grade, no distance, no title, no photo, no seller**. See Gaps for what the
buyer-marketplace UI (Phase 5) actually needs.

---

### 5.9 `GET /cards/{card_id}/verify` — public health-card verify · **no auth** · `200`
**Query:** `sig` (the signature from the QR link). **`200` →**
(`CardVerificationResponse`):
```jsonc
// match:
{ "verified":true, "reason":"signature matches",
  "card": { "card_id","item_id","grade":"Good","graded_at",
            "defect_summary":"Light scuffs… Observed defects: minor at toe cap.",
            "warranty_stance":"14-day returns","annotated_photo_keys":[…],
            "signature","qr_target" } }
// tamper / bad sig:
{ "verified":false, "card":null, "reason":"presented signature does not match the stored signature" }
```
Unknown `card_id` → `404`. (Note the verify payload's `card` has a flattened
`grade` + `defect_summary`, slightly different from the `card` facet in
`GET /items/{id}`, which has no grade and no defect_summary.)

---

## 6. Config the frontend needs

From `.env.example` / `wiring.py::Settings`:
- **`API base URL`** — the deployed API Gateway / Lambda URL (set as
  `NEXT_PUBLIC_API_BASE_URL`). Local dev: run `uvicorn` against a wired app.
- **Cognito (client-side, public, safe to ship):**
  `REBRIDGE_COGNITO_REGION` (default `us-east-1`),
  `REBRIDGE_COGNITO_USER_POOL_ID` (e.g. `us-east-1_xxx`),
  `REBRIDGE_COGNITO_APP_CLIENT_ID`. The FE needs the user-pool id + app-client id
  + region (+ Hosted-UI domain, if used) to run the Cognito login. App-client id
  and user-pool id are **public** by design.
- **MUST NOT be in the frontend:** AWS credentials/IAM keys, the KMS key id
  (`REBRIDGE_KMS_KEY_ID`), DynamoDB table name, S3 bucket name, SQS queue URL,
  EventBridge bus, Bedrock model ids — all server-only.
- **Demo data categories** (seed price bands + personas):
  **`electronics`, `apparel`, `home`, `toys`, `books`**. ⚠️ Unknown categories
  (e.g. `"sneakers"`) fall back to a generic price band — for realistic demo
  numbers, seed items under these five categories. Persona geohashes in the seed
  start with `9q8yy` (and others) — match listing `geohash5` to them so demand
  matching/marketplace `geo` filtering returns hits.

---

## 7. Gaps & open questions (need your decision before Phase 1 wiring)

These are the places where the frontend spec (FRONTEND_INSTRUCTIONS.md) assumes
something the backend does **not** currently expose. I will **not** invent API
shapes — please rule on each.

**🔴 G1 — No matching / buyer-results endpoint (biggest gap).**
The Demand Matching Engine (Engine B) is fully built and wired in `wiring.py`,
but it is **not exposed by any router**, **not in the `Services` container**, and
is **not invoked anywhere at runtime** (the grading pipeline does grade→card→route
only; it never calls `match()`). Phase 5 needs the **match chip / "N buyers
< 5 km" / proactive match-push** and Phase 3's receipt line `Route: P2P · N
buyers < 5 km`. **There is no live data source for any of this.**
→ *Question:* should I (a) build the FE against a contract-accurate **mock** for
matching now and have the backend team add `POST /items/{id}/match` →
`{ ranking:[…], notified:[…], count }` later, or (b) is a matching endpoint
already planned/elsewhere? What's the exact response shape you want?

**🔴 G2 — No review-queue endpoint.**
`ReviewConsoleService` (list pending / confirm / override) is built but **not
routed**. Phase 6's Review Console (queue sorted by value × uncertainty,
confirm/override) has no API to call. → *Question:* add
`GET /review` + `POST /review/{id}/confirm` + `POST /review/{id}/override`, or is
this out of scope for the demo? (Mock it for now?)

**🟠 G3 — Marketplace tiles can't show grade or distance from one call.**
`GET /marketplace` returns only the LISTING facet (no grade, no distance, no
title/photo). The spec wants tiles "lead with grade + **distance**". Options:
fetch `GET /items/{id}` per listing to get the grade (N+1), and compute distance
**client-side** from `geohash5` (the only location data — ~5 km precision; the
backend deliberately stores nothing finer). → *Question:* OK to do per-item grade
fetch + client-side geohash distance, or do you want an enriched marketplace
response added?

**🟠 G4 — "Price vs new" has no backend field.**
The Health Card and decision cards in the design show **price vs new / vs
liquidation**. The backend has the recoverable band point (`decision.price`,
`decision.value`) and the operator's listing `price`, but **no original/RRP/new
price** and **no liquidation baseline**. → *Question:* where should "new price"
come from — FE-supplied/seeded demo constant, or a backend field to add?

**🟠 G5 — No way to display uploaded/annotated photos.**
`presign` issues **PUT-only** URLs; there is **no GET-presign / download
endpoint**, and `annotated_photo_keys` are raw S3 keys with no public URL. So the
FE cannot render the user's uploaded photos or card photos. → *Question:* add a
GET-presign (or make the bucket/CloudFront serve keys), or use local
preview-only images (object URLs) for the demo and not round-trip real photos?

**🟡 G6 — No synchronous grade path / no job-status endpoint.**
Grading is enqueue-only; the FE must **poll `GET /items/{id}`**. For the demo
this means the worker must actually be running, and real grade latency drives the
Phase-3 "reveal theatre". → *Question:* for the live demo, do we (a) run the SQS
worker, (b) stand up a thin sync grade endpoint, or (c) drive Phase 3 from a
contract-accurate mock and only poll for the real-backend gate test?

**🟡 G7 — Defect locations are free text, not coordinates.**
Phase 4's 3D scanner pins "defect hotspots on the model". Backend defects are
`{location:string, severity:string}` (e.g. `"toe cap"`) — **no x/y/z or image
coords**. → *Question:* I'll map a small set of known location strings → fixed
mesh anchor points on the placeholder sneaker (FE-side lookup). Acceptable?

**🟢 G8 — Auth has no login endpoint (confirm approach).**
As in §2, the FE must authenticate against **Cognito directly** (Hosted UI or
Amplify Auth). → *Question:* which? And can you provide a real user-pool id +
app-client id (+ Hosted UI domain) and a demo user, or should the demo run with
auth stubbed (the routes are overridable, and tests bypass auth)?

**🟢 G9 — `GET /marketplace` requires `category`.**
There is no "list everything" mode — a `category` is mandatory. The buyer
marketplace must pick a default category (one of the five seeded) or iterate
categories. Confirm the default browse category for the demo (suggest
`electronics`).

---

## 8. Quick reference — what maps to which screen

| Frontend screen (phase) | Backend it uses | Status |
|---|---|---|
| Returns Desk capture + grade (P2) | `POST /items`, `:presign`, `POST .../grade` (202), poll `GET /items/{id}` | ✅ live |
| Grading reveal + receipt (P3) | `GET /items/{id}` (`grade`,`decision`) | ✅ live; "N buyers" line ⚠️ G1 |
| 3D scanner (P4) | `GET /items/{id}` grade/defects | ✅ for grade; hotspots ⚠️ G7 |
| Health Card (P5) | `GET /items/{id}.card` + `GET /cards/{id}/verify` | ✅ live; "price vs new" ⚠️ G4 |
| Rahul decision card (P5) | grade + `decision` + **match chip** | ⚠️ match ⚠️ G1 |
| Buyer marketplace (P5) | `GET /marketplace` (+ per-item grade) | ⚠️ G3 (grade/distance) |
| Match push card (P5) | matching engine | 🔴 G1 (no endpoint) |
| Review Console (P6) | review console service | 🔴 G2 (no endpoint) |
| Hero / Notification (P6) | static / decorative | ✅ no backend |

---

## 9. How to run the backend locally (for the gate tests)

```powershell
python -m venv .venv ; .venv\Scripts\activate
pip install -e ./rebridge_data[test] -e ./rebridge_service[test] -e ./rebridge_api[test]
python run_tests.py            # 537 tests, all green
```
- A fully-wired app needs live AWS. For FE integration without AWS, build the app
  with the in-memory fakes (`rebridge_api/tests/fakes.py`) — that's how the wire
  shapes above were captured — or run against contract-accurate mocks.
- `openapi.json` (generated from the wired app) is committed next to this file as
  the machine-readable contract; mirror it in the Zod schemas in Phase 1.

---

**🚦 GATE 0 — STOPPING HERE.** No frontend code will be written until you confirm
this contract and rule on the gaps in §7 (especially **G1 matching** and **G2
review**, which have no backend at all today).
