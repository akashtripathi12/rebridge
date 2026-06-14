# ReBridge — Contract Addendum (Gap Resolutions)

**Status:** agreed contract for the 9 gaps from `BACKEND_MAP.md`. This is the single source of truth both sides build to.
**Convention:** matches the existing backend contract — money is a **JSON string** (`"340.00"`), confidence is a **number** (`0.91`), timestamps are ISO-8601 strings, all private routes require `Authorization: Bearer <Cognito JWT>`. Grades: `Like New · Very Good · Good · Acceptable · Unsellable`. Dispositions: `RESELL · REFURB · P2P · DONATE`.

**How to use this:** Frontend builds Zod schemas + mock services to these exact shapes **now**. Backend implements these exact shapes tomorrow. Because both sides build to the same contract, swapping a frontend mock for the live endpoint is a one-line change.

---

## G1 🔴 — Matching endpoint (Engine B) — **BACKEND TO ADD**

Engine B is already built and wired; it just needs a route that invokes it and returns ranked buyers.

**`GET /items/{item_id}/matches`** — private. Returns ranked buyer matches for a graded item.

Returns `200`:
```json
{
  "item_id": "itm_abc123",
  "generated_at": "2026-06-14T09:12:04Z",
  "matches": [
    {
      "buyer_id": "buy_001",
      "display_label": "Buyer 4 km away",
      "distance_km": 4.2,
      "match_score": 0.94,
      "match_reasons": ["wishlisted this product", "recent stroller purchase"],
      "intent_tier": "HIGH"
    }
  ],
  "match_count_within_5km": 3,
  "top_reason": "wishlisted this product"
}
```
- `intent_tier` enum: `HIGH · MEDIUM · LOW`.
- `match_score`: number 0–1. `distance_km`: number.
- Empty result → `200` with `matches: []`, `match_count_within_5km: 0`, `top_reason: null`.
- `404` if item not found; `409`/empty if item not yet graded (frontend only calls this once `meta.status == GRADED`).

**Frontend use:** the match chip ("3 interested buyers within 5 km" ← `match_count_within_5km`), the proactive-push card (top match `display_label` + `top_reason`), Rahul's decision screen.

---

## G2 🔴 — Review-queue endpoints — **BACKEND TO ADD**

Review console service exists; route it.

**`GET /review/queue`** — private. Items below the confidence gate, sorted by value × uncertainty.

Returns `200`:
```json
{
  "queue": [
    {
      "item_id": "itm_def456",
      "title": "Mixer grinder · 750W",
      "ai_grade": "Good",
      "confidence": 0.64,
      "est_value": "1900.00",
      "priority": "HIGH",
      "photo_keys": ["uploads/itm_def456/0.jpg"],
      "created_at": "2026-06-14T08:40:00Z"
    }
  ],
  "total": 7
}
```
- `priority` enum: `HIGH · MEDIUM · LOW` (server computes from est_value × (1 − confidence)).

**`POST /review/{item_id}`** — private. Reviewer confirms or overrides.
Request:
```json
{ "action": "CONFIRM", "override_grade": null }
```
- `action` enum: `CONFIRM · OVERRIDE`. If `OVERRIDE`, `override_grade` must be a valid grade enum; if `CONFIRM`, it's `null`.
Returns `200`: the updated item (same shape as `GET /items/{id}`), with `meta.status` advanced to `GRADED`.

---

## G3 🟠 — Marketplace grade + distance — **BACKEND TO EXTEND** (quick add, highest demo value)

Extend each item in the existing **`GET /marketplace`** response with three fields:
```json
{
  "listing_id": "lst_789",
  "item_id": "itm_abc123",
  "title": "Running Shoes · UK 7",
  "grade": "Good",                 // ADD
  "distance_km": 4.0,              // ADD
  "price": "340.00",
  "price_new": "500.00",          // ADD (see G4)
  "health_card_id": "card_xyz",
  "category": "shoes",
  "thumb_key": "uploads/itm_abc123/0.jpg"
}
```
- If a true distance isn't computable server-side for the demo, return a seeded `distance_km` — frontend treats it as authoritative.

**Frontend fallback if G3 slips:** enrich client-side via `GET /items/{id}` for grade, mock `distance_km`. Build the fallback now; remove it when G3 lands.

---

## G4 🟠 — Price vs new — **BACKEND (folded into G3)**

Add `price_new` (JSON string) wherever a graded price is shown: marketplace items (above), `GET /items/{id}` decision block, and the Health Card payload. Source = original catalog MRP.
**Frontend fallback:** mock `price_new` from seed data; show "% saved".

---

## G5 🟠 — Photo display-back — **FRONTEND HANDLES (no backend change)**

Presign is PUT-only by design. Frontend keeps a local `URL.createObjectURL(file)` at upload time and renders the grading reveal + thumbnails against that local URL for the session. No GET-presign needed for the demo. (Production roadmap: add a read-presign endpoint.)

---

## G6 🟡 — Async grading is poll-only — **FRONTEND HANDLES**

No job-status endpoint. Frontend polls **`GET /items/{id}`** every ~1.5s (TanStack Query `refetchInterval`) until `meta.status` leaves `GRADING`. Terminal states: `GRADED · PENDING_REVIEW · RETAKE_REQUIRED`. The staged status copy in the reveal ("Inspecting soles…") is frontend theatre over the poll — no real sub-statuses required.

---

## G7 🟡 — Defect locations are free text — **FRONTEND HANDLES**

Backend defect `location` is free text, not 3D coordinates. In `<ProductScanner>`, define 3 fixed model anchors (toe / sole / heel) and map each defect to the nearest anchor by keyword. The 3D scan showcases the *capability*; pixel-true mapping is a roadmap item (future model output: structured coordinates).

---

## G8 🟢 — Cognito login — **FRONTEND HANDLES**

No backend login endpoint; FE authenticates to Cognito directly. Build behind an `authProvider` interface:
- **Now:** dev mock token so Phases 1–5 proceed unblocked.
- **Later:** real Cognito hosted UI via Amplify Auth or `react-oidc-context`; store JWT; attach as `Authorization: Bearer`. Wire real Cognito last.

---

## G9 🟢 — Marketplace requires category — **FRONTEND HANDLES**

`GET /marketplace` requires `category`. Frontend always sends one; the "Nearby" default chip maps to a sensible default (e.g. first category or an `all` value if backend supports it — **confirm with backend** whether `all` is accepted, else default to a real category).

---

## Ownership summary

| Gap | Owner | Action |
|---|---|---|
| G1 matching | **Backend (AM)** | add `GET /items/{id}/matches` |
| G2 review | **Backend (AM)** | add `GET /review/queue` + `POST /review/{id}` |
| G3 mkt grade+distance | **Backend (AM, quick)** | extend `/marketplace` items |
| G4 price_new | **Backend (with G3)** | add `price_new` field |
| G5 photo display | Frontend | local object URL |
| G6 poll | Frontend | poll `meta.status` |
| G7 defect anchors | Frontend | 3 model anchors + keyword map |
| G8 auth | Frontend | authProvider + mock token → Cognito last |
| G9 category | Frontend | always send category (confirm `all`) |

**Backend AM priority order (by demo value):** G3 → G1 → G2. G4 rides with G3.
