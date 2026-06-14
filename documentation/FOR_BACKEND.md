# FOR_BACKEND.md — sunrise checklist

Frontend is built against the addendum shapes with mock services. Implement the
four endpoints below to **these exact shapes** and the swap is one env flag each
(table at the bottom). The frontend Zod-validates every response, so a field
name/type mismatch will throw — match byte-for-byte.

**Conventions (already agreed):** money = JSON **string** (`"340.00"`),
confidence = **number**, timestamps = ISO-8601 string, private routes require
`Authorization: Bearer <Cognito JWT>`. Grades: `Like New · Very Good · Good ·
Acceptable · Unsellable`. Dispositions: `RESELL · REFURB · P2P · DONATE`.

---

## G1 — `GET /items/{item_id}/matches` (private)

**Frontend uses it for:** the reveal/decision "Route: P2P · **N** buyers < 5 km"
line and (Phase 5) the match-push card. Called only once `meta.status == GRADED`.

**Example request:** `GET /items/itm_shoe7/matches`
`Authorization: Bearer <jwt>`

**Exact JSON my mock returns today** (match this shape; `generated_at` is dynamic):
```json
{
  "item_id": "itm_shoe7",
  "generated_at": "2026-06-14T03:59:00.000Z",
  "matches": [
    { "buyer_id": "buy_001", "display_label": "Buyer 2 km away", "distance_km": 2.0, "match_score": 0.94, "match_reasons": ["wishlisted this product", "recent stroller purchase"], "intent_tier": "HIGH" },
    { "buyer_id": "buy_002", "display_label": "Buyer 4 km away", "distance_km": 4.0, "match_score": 0.88, "match_reasons": ["browsing this category", "deal-seeker"], "intent_tier": "HIGH" },
    { "buyer_id": "buy_003", "display_label": "Buyer 5 km away", "distance_km": 4.6, "match_score": 0.72, "match_reasons": ["price-sensitive shopper nearby"], "intent_tier": "MEDIUM" },
    { "buyer_id": "buy_004", "display_label": "Buyer 8 km away", "distance_km": 8.1, "match_score": 0.55, "match_reasons": ["category match"], "intent_tier": "LOW" }
  ],
  "match_count_within_5km": 3,
  "top_reason": "wishlisted this product"
}
```
- `intent_tier` ∈ `HIGH·MEDIUM·LOW`. `match_score`,`distance_km` numbers.
- Empty: `200` with `matches: []`, `match_count_within_5km: 0`, `top_reason: null`.
- `404` unknown item. Ungraded → `409` or empty (FE only calls when GRADED).

**Open choices for you:** (1) is `match_count_within_5km` strictly distance ≤ 5,
or your own radius bucket? FE renders the number verbatim. (2) `display_label`
wording — FE shows it as-is on the push card; keep it PII-free.

---

## G2 — review queue (private)

**`GET /review/queue`** — **FE uses it for:** Phase 6 Review Console (queue sorted
by value × uncertainty).

**Example:** `GET /review/queue` → exact mock JSON:
```json
{
  "queue": [
    { "item_id": "itm_mixer", "title": "Mixer grinder · 750W", "ai_grade": "Good", "confidence": 0.64, "est_value": "1900.00", "priority": "HIGH", "photo_keys": ["uploads/itm_mixer/0.jpg"], "created_at": "2026-06-14T08:40:00Z" },
    { "item_id": "itm_cycle", "title": "Kids cycle · 16\"", "ai_grade": "Acceptable", "confidence": 0.71, "est_value": "1200.00", "priority": "HIGH", "photo_keys": ["uploads/itm_cycle/0.jpg"], "created_at": "2026-06-14T08:44:00Z" },
    { "item_id": "itm_case", "title": "Phone case (handmade)", "ai_grade": "Like New", "confidence": 0.77, "est_value": "240.00", "priority": "MEDIUM", "photo_keys": ["uploads/itm_case/0.jpg"], "created_at": "2026-06-14T08:51:00Z" }
  ],
  "total": 3
}
```
- `priority` ∈ `HIGH·MEDIUM·LOW`, **server-computed** from est_value × (1 −
  confidence).

**`POST /review/{item_id}`** — request:
```json
{ "action": "CONFIRM", "override_grade": null }
```
- `action` ∈ `CONFIRM·OVERRIDE`. If `OVERRIDE`, `override_grade` is a valid grade
  enum; if `CONFIRM`, `null`.
- **Returns `200`: the updated item, same shape as `GET /items/{id}`** (the
  `ItemAggregate`), with `meta.status` advanced to `GRADED`.

**Open choices for you:** the exact **priority thresholds** — what cutoffs map
`value × (1−confidence)` to HIGH/MEDIUM/LOW? FE only displays the tag; you own
the bucketing. Tell me the cutoffs so the demo data lands as intended.

---

## G3 + G4 — extend `GET /marketplace` items (private)

**FE uses it for:** Phase 5 buyer marketplace tiles (grade + distance + price vs
new). G9: FE **always sends `category`**.

**Example:** `GET /marketplace?category=shoes` → exact mock JSON:
```json
{
  "listings": [
    { "listing_id": "lst_shoe7", "item_id": "itm_shoe7", "title": "Running Shoes · UK 7", "grade": "Good", "distance_km": 4.0, "price": "340.00", "price_new": "500.00", "health_card_id": "card_shoe7", "category": "shoes", "thumb_key": "shoe" }
  ]
}
```
Full mock set spans categories `shoes · baby · tech · books` (4 items). Each item
adds **`grade`**, **`distance_km`** (number), **`price_new`** (string, the
catalog MRP — G4), `health_card_id`, `title`, `thumb_key` to the existing
listing fields.
- If true distance isn't computable server-side, return a **seeded
  `distance_km`** — FE treats it as authoritative.

**Open choices for you:**
1. **G9 — does `GET /marketplace` accept `category=all`?** FE's "Nearby" default
   chip currently sends `category=all` and the mock returns everything. If the
   live backend rejects `all`, tell me the default category to send instead (I'll
   change one line). **This is the one I most need answered.**
2. `thumb_key` — is it an S3 object key (then we still have no GET-presign to
   render it, G5) or a stable glyph id? Today FE maps it to a built-in product
   glyph. If you return real keys, we'll need a read-presign or CDN URL to show
   buyer photos (otherwise FE keeps glyphs).
3. `price_new` source — confirm it's catalog MRP; also add it to the
   `GET /items/{id}` **decision block** and the Health Card payload (the FE
   schema already accepts `decision.price_new` as optional).

**Also (no new endpoint, just a note):** the reveal receipt shows a "vs
liquidation" line. There's no backend field for it — FE shows a seeded demo
constant. If you have a liquidation baseline, expose it and I'll wire it.

---

## Flip-to-go-live (env flags → screen unblocked)

Set in `frontend/.env.local`, restart dev. Default all false (mock).

| Flag | Endpoint it switches | Screens it unblocks |
|---|---|---|
| `NEXT_PUBLIC_ITEMS_LIVE=true` | `/items`, `:presign`, `/grade`, `GET /items/{id}`, `/route`, listings, `/cards/{id}/verify` | Returns Desk (P2), Reveal (P3) — needs the **SQS worker running** so the poll reaches a terminal state |
| `NEXT_PUBLIC_MATCHING_LIVE=true` | `GET /items/{id}/matches` (G1) | "N buyers < 5 km" in Reveal/Returns; match push + decision (P5) |
| `NEXT_PUBLIC_REVIEW_LIVE=true` | `GET /review/queue`, `POST /review/{id}` (G2) | Review Console (P6) |
| `NEXT_PUBLIC_MARKETPLACE_LIVE=true` | `GET /marketplace` extended (G3/G4) | Buyer marketplace (P5) |

Cognito (G8), when ready — public values only:
`NEXT_PUBLIC_COGNITO_REGION`, `NEXT_PUBLIC_COGNITO_USER_POOL_ID`,
`NEXT_PUBLIC_COGNITO_APP_CLIENT_ID` (+ `NEXT_PUBLIC_API_BASE_URL`). Until then the
dev mock token (`authProvider`) keeps every screen working.

**Priority order (your call, by demo value): G3 → G1 → G2.** G4 rides with G3.

---

# Night 2 — resolved assumptions + new note

Built Phases 5/6/7 against these. Each is a single-source constant so confirming
the real value is a one-line change.

### G9 — `category=all` (ASSUMED ACCEPTED)
The marketplace filter sends `GET /marketplace?category=all` for the "Nearby"
default, routed through `frontend/lib/market/constants.ts`
(`MARKETPLACE_ALL_CATEGORY = "all"`). **If the backend rejects `all`:** tell me
the behaviour (omit the param, or a real default category) — it's a one-line
change in that constant/service. Seeded categories in use: `shoes · baby · tech ·
books`.

### G2 — priority cutoffs (ASSUMED, single source)
Until you confirm, the review console computes priority **from grade confidence**
in `frontend/lib/review/thresholds.ts`:
`HIGH: conf < 0.70 · MEDIUM: 0.70 ≤ conf < 0.85 · LOW: conf ≥ 0.85`.
The console sorts HIGH-first, then most-uncertain. **Send me the real cutoffs (or
confirm the server returns `priority` and I should trust it verbatim)** — one-line
change. `POST /review/{item_id}` is expected to return the updated `ItemAggregate`
(status→GRADED), exactly as the addendum states; the console already handles
CONFIRM and OVERRIDE (with `override_grade`).

### New note (not blocking) — Health Card needs two reads
The Health Card composes the EXISTING `GET /cards/{card_id}/verify` (grade,
warranty, signature, verified) **+** `GET /items/{id}` (confidence + structured
defects), because the verify payload has `defect_summary` (string) but no
`confidence` or structured `defects[]`. If you add `confidence` + `defects[]` to
the verify payload (or expose one card endpoint), the frontend drops the second
call. Low priority — current compose works.

### Still open from Night 1 (unchanged)
`thumb_key` / annotated photos: still no GET-presign or CDN URL, so marketplace
tiles + Health Card render product **glyphs**, not real photos (G5). A read-
presign endpoint would light up real imagery. `price_new` (G4) and the reveal's
"vs liquidation" line still want a backend source (FE uses seed/MRP for now).
