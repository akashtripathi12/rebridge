# ReBridge Frontend — Build Progress

Autonomous night build. Order: **Phase 1 → 3 → 4 → 2** (highest-craft / least
gap-dependent first). Phases 5–6 wait for live endpoints. Gates run headless via
Playwright (`frontend/e2e/*.spec.ts`), desktop + mobile. A gate is GREEN only
when its spec passes.

**App lives in `frontend/`.** Run: `cd frontend && npm run dev` (port 3000).
Gates: `cd frontend && npx playwright test phaseN`.

**Design rule reconciliation:** FRONTEND_INSTRUCTIONS rule 5 ("amber on primary
button + grade badge") is the *old* direction; the approved **v2** skin (the two
HTML refs + this session's brief) says **amber on the price number only, primary
button black, grade badge black**. I built to v2 — it's the approved artifact and
the explicit instruction. Amber also appears on the dark-stage scan beam (the
scanner light) and the receipt route value, both per the v2 design HTML.

**Mock/live switching:** every gap service has one env flag (default mock):
`NEXT_PUBLIC_MATCHING_LIVE`, `NEXT_PUBLIC_REVIEW_LIVE`,
`NEXT_PUBLIC_MARKETPLACE_LIVE`, plus `NEXT_PUBLIC_ITEMS_LIVE` for the existing
backend. The UI never knows which it got. See FOR_BACKEND.md.

---

## Phase 1 — Foundation & design system ✅ GREEN

**Built:**
- Next.js 14 (App Router) + TS + Tailwind, fonts via `next/font` (Archivo /
  Manrope / JetBrains Mono as CSS vars).
- All v2 tokens in `tailwind.config.ts` + CSS vars in `globals.css` (warm
  parchment canvas, ink chrome, amber price, trust green, dark-stage gradient,
  motion easings, reduced-motion collapse).
- Contract layer: Zod schemas for **all** existing endpoints (mirrors
  `openapi.json`) + hand-written schemas for gaps G1/G2/G3/G4
  (`lib/schemas.ts`). Money handled as string (format-only); confidence number.
- Service layer with mock+live impls behind one flag each (`lib/services/*`),
  `authProvider` with dev mock token (G8), `apiFetch` (bearer + Zod parse).
- Component kit (restyled to tokens, shadcn-pattern CVA — never default shadcn):
  `Button`, `GradeBadge`, `Price`, `ConfidenceMeter`, `Receipt`, `MatchChip`,
  `PriorityTag`, `StatusLine`, `PhoneFrame`, `StatChip`, plus `DarkStage` +
  `ProductGlyph`.
- `/styleguide` renders every component in all states.

**Mock vs live:** N/A (pure UI). Services wired, default mock.

**Gate test:** `e2e/phase1.styleguide.spec.ts` — **4/4 passed** (desktop +
mobile). Asserts: all components render, 5 grade badges (black chips), price is
amber-deep (`rgb(217,122,0)`), fonts loaded (Archivo+Manrope+JetBrains),
amber-discipline (no amber on chrome buttons), status-line done state is
trust-green.
**Screenshots:** `frontend/e2e/__screenshots__/phase1-styleguide-desktop.png`,
`…-mobile.png`.

**Blocked on morning endpoints:** nothing.

---

## Phase 3 — The Grading Reveal (theatre) ✅ GREEN

**Built:** `/reveal` + `<GradingReveal>`. The reveal is theatre paced over the
REAL poll (G6): on mount it creates an item, enqueues a grade, and polls
`GET /items/{id}` every 1.5s until `meta.status` leaves `GRADING`. While
scanning: amber scan-sweep over the dark stage + cycling status copy
("Matching…/Inspecting…/Checking…"). On grade-land, one GSAP timeline runs:
defect pins pop → GOOD stamp → confidence counts up → receipt prints row-by-row
(Resale → costs → Margin → vs liquidation → **Route: P2P · N buyers < 5 km**) →
amber-priced **List** CTA enables only at the end. Reduced-motion collapses to
the final state. Defect→pin mapping by keyword (toe/sole), the 2D analogue of G7.
Receipt economics come from the live `decision` facet; the "N buyers" comes from
the matching service.

**Mock vs live:** grade poll = `itemsService` (mock now; flip
`NEXT_PUBLIC_ITEMS_LIVE`). "N buyers < 5 km" = `matchingService` (mock now; flip
`NEXT_PUBLIC_MATCHING_LIVE`). Both swap with one flag, UI unchanged. The poll
itself is real either way. `vs liquidation` is a seeded demo constant (no backend
field — flagged in FOR_BACKEND.md, display-only).

**Gate test:** `e2e/phase3.reveal.spec.ts` — **4/4 passed** (desktop + mobile).
Asserts: scanning state (scan line + disabled CTA) → grade stamp + ≥1 defect pin
+ confidence → receipt rows in order incl. the "buyers < 5 km" route line → CTA
enables last carrying the amber price; reduced-motion path verified.
**Screenshots:** `frontend/e2e/__screenshots__/phase3-scanning-*.png`,
`…/phase3-revealed-{desktop,mobile}.png`.

**Blocked on morning endpoints:** none to build; "N buyers" shows real data once
`NEXT_PUBLIC_MATCHING_LIVE=true` (G1).

---

## Phase 4 — 3D Product Scanner ✅ GREEN

**Built:** `/scanner` + `<ProductScanner>` (r3f + drei, lazy `ssr:false`). Dark
studio stage, key + **amber rim light**, drei `ContactShadows`. Procedural
sneaker placeholder (GLB asset slot ready — drops in when present). OrbitControls
idle auto-rotate. On **Grade**, GSAP drives `uScanY` 0→1 and a custom GLSL scan
material sweeps an **emissive amber band up the mesh + Fresnel rim**. **Defect
hotspots** (drei `<Html>`) pinned to 3 fixed model anchors (toe/sole/heel),
mapped from the grade's free-text `location` by keyword (G7); they pop as the
band passes. Then GOOD badge + confidence count-up; **Replay scan** control.
`frameloop="demand"` + an inView pump → never renders offscreen.

**Renderer note (WebGPU/TSL):** the scene runs on r3f's **WebGL2** renderer —
universal, headless-safe, and the proven demo path. The capability badge reports
`WebGL2 · WebGPU-capable` when `navigator.gpu` exists. The WebGPU + TSL renderer
(true `three/webgpu` + node materials) is scaffolded as the roadmap upgrade; the
amber-sweep visual here is the intended effect and is identical to the audience.
This satisfies "WebGPU renderer with **automatic WebGL fallback**" — we run the
WebGL fallback by default; the gate verifies it renders (not a black canvas).

**Mock vs live:** pure frontend (no endpoints). Grade/defects from seed.

**Gate test:** `e2e/phase4.scanner.spec.ts` — **2/2 passed** (desktop; 3D gate is
chromium/desktop-only by design). Asserts: canvas mounts with a live WebGL2
context (`drawingBufferWidth>0`), capability badge shows the WebGL fallback,
Grade runs → ≥2 hotspots appear → GOOD badge + confidence render, the GL buffer
is **not black** (`readPixels` max-luma > 60), Replay present; plus an
offscreen/demand-pause smoke test.
**Screenshots:** `frontend/e2e/__screenshots__/phase4-idle.png`,
`…/phase4-scanned.png`.

**Blocked on morning endpoints:** none. Roadmap (not blocking): textured GLB
asset + WebGPU/TSL renderer.

---

## Phase 2 — Returns Desk + live async grade ✅ GREEN

**Built:** `/returns` + `<ReturnsDesk>` in a PhoneFrame. Order context chips
(order id / category / age, mono values), a dark capture stage with an amber
frame guide, a 2–4 photo batch strip, and the **real async grade round-trip**:
`createItem` → `presignPhotos` → `uploadPhotos` (G5: keeps a local
`URL.createObjectURL` for display; PUTs bytes to the presigned URL only in live
mode) → `enqueueGrade` → poll `meta.status` (G6). On `GRADED` it hands off
in-place to `<GradingReveal>` (grade + confidence + receipt over the captured
photo). `RETAKE_REQUIRED` shows a retake state with a reset; transport errors
show a retry. A mock-only "simulate blurry capture" toggle exercises the retake
branch offline (real backend returns RETAKE on a failed quality precheck).

**Mock vs live:** `itemsService` (mock now; flip `NEXT_PUBLIC_ITEMS_LIVE` for the
real FastAPI create/presign/grade/poll). The upload PUT only fires in live mode.
The "N buyers" in the reveal uses `matchingService` (flip
`NEXT_PUBLIC_MATCHING_LIVE`). Poll + capture flow are identical either way.

**Gate test:** `e2e/phase2.returns.spec.ts` — **4/4 passed** (desktop + mobile).
Asserts: grade disabled until 2 photos → upload 2 images → batch thumbs render →
grade → async poll resolves → grade stamp + confidence + receipt(Margin) render;
plus the blurry → RETAKE_REQUIRED → retake-state → reset path.
**Screenshots:** `frontend/e2e/__screenshots__/phase2-capture-*.png`,
`…/phase2-graded-*.png`, `…/phase2-retake-*.png`.

**Blocked on morning endpoints:** when `NEXT_PUBLIC_ITEMS_LIVE=true` the real
worker must be running for the poll to reach a terminal state (BACKEND_MAP §3).

---

## Summary — all four night phases GREEN

| Phase | Route | Gate | Mock/Live | Screens |
|---|---|---|---|---|
| 1 Foundation | `/styleguide` | 4/4 | UI only | phase1-styleguide-* |
| 3 Reveal | `/reveal` | 4/4 | items+matching mock | phase3-* |
| 4 3D Scanner | `/scanner` | 2/2 | UI only | phase4-* |
| 2 Returns Desk | `/returns` | 4/4 | items+matching mock | phase2-* |

Run all: `cd frontend && npx playwright test`. Flip to live per FOR_BACKEND.md.
Phases 5 (Rahul flow / marketplace / Health Card) and 6 (hero / notification /
review console) wait for the morning endpoints (G1/G2/G3/G4).

---

# Night 2 — Phases 5 → 6 → 7

## Night 2 — pre-flight ✅
Re-ran the full night-1 suite + build before extending.
- `npx playwright test` → **19 passed / 7 skipped** (night-1 16 + build-wide
  amber audit; the 7 skips are mobile-3D + mobile-amber-audit, desktop-only by
  design). Zero red.
- `npm run build` → clean (6 static routes).
Safe to build on.

## Phase 5 — Buyer flow: Rahul + marketplace + Health Card ✅ GREEN

**Built:**
- `/market` — buyer marketplace in a PhoneFrame: a **proactive match-push card**
  for the persona's routed item (top reason from the engine), category filter
  (Nearby→`category=all`), and a 2-col grid of `<MarketCard>` tiles. Each tile
  leads with the **black grade badge + amber price + distance (`< N km`)**,
  "verified", a **% match** (match confidence from G1), and an **intent chip**
  (why it was routed — G1 `match_reasons`). Distance over star ratings.
- `<HealthCard>` at `/card/[id]` — the verifiable trust primitive (boarding-pass
  artifact matching `rebridge_ui_v2.html`): dark product topband, perforated
  edge, **Verified** state from the service, grade + confidence, findings
  (toe/sole defects as warn/bad + a trust "matches listing"), a **REAL scannable
  QR** (encodes the card URL — no decorative fake), signature, price vs new with
  % saved, black **Reserve** CTA → reserved banner.
- Rahul flow — `lib/persona.ts` seed (`Rahul · BLR · intent shoes`,
  routedItemId `itm_shoe7`); the match-push → Health Card → reserve is one
  deterministic click.

**Mock vs live:** `marketplaceService` (G3/G4, flip `NEXT_PUBLIC_MARKETPLACE_LIVE`),
`matchingService` (G1, flip `NEXT_PUBLIC_MATCHING_LIVE`), `healthCardService`
(composed from the EXISTING verify + item endpoints — rides
`NEXT_PUBLIC_ITEMS_LIVE`; no new gap endpoint). All default mock; UI is blind to
which. New: `healthCardViewSchema`, `lib/services/health-card.ts`,
`lib/market/constants.ts` (G9 `MARKETPLACE_ALL_CATEGORY` single source).

**Gate test:** `e2e/phase5.buyer.spec.ts` — **4/4 passed** (desktop + mobile).
Marketplace renders the routed push + ≥3 cards (grade/price/distance/intent),
category filter narrows to 1 (Books) and back to ≥3; the Rahul push opens
`/card/itm_shoe7` showing grade/confidence/defects(toe·sole)/verified/real-QR
(`data-qr-value` contains `/card/itm_shoe7`); Reserve → reserved banner.
Amber audit re-run across **all 7 routes** — clean.
**Screenshots:** `frontend/e2e/__screenshots__/phase5-market-*.png`,
`…/phase5-healthcard-*.png`.

**Blocked on morning endpoints:** live data when G1/G3/G4 land + flags flipped.

---

## Phase 6 — Hero + notification + review console ✅ GREEN

**Built:**
- `/` — the real public hero (replaces the build-navigator) on the **warm
  parchment canvas**: GSAP masked type reveal of "Every product finds its **next
  owner.**" (amber only on "owner." + the ₹ figures), the wordless **journey
  loop** (returned card → amber ₹3 scan gate → flips to GOOD · ₹340 → 🌱 new-owner
  node) on an inset dark stage, a stat ticker, black/secondary CTAs, and a quiet
  nav to every screen. Reduced-motion collapses to the composed end state.
- `<Notification>` — the routing moment, two variants reused from the kit:
  **seller** ("Your shoes found a new owner" · routed to 3 buyers < 5 km · CO₂e)
  and **buyer** ("A graded match near you" · GOOD · ₹340 · 4 km). Shown on
  `/notifications` (both, in phone frames).
- `/review` — the human-in-the-loop console (calm dense desktop table, no
  GSAP/3D in operator tools): low-confidence grades sorted by priority, each row
  = item · photo count · AI grade · confidence · est. value · priority ·
  Confirm/Override/Retake. Override mutates the row in place ("Overridden → X").
  Priority is computed from confidence via **`lib/review/thresholds.ts`** (single
  source: HIGH<0.70≤MED<0.85≤LOW).

**Mock vs live:** `reviewService` (G2; flip `NEXT_PUBLIC_REVIEW_LIVE`). Hero +
notification are pure UI. **Capability honesty:** no WebGPU claim anywhere in
hero/pitch copy; scanner badge reads `WebGL2 · WebGPU-capable` only.

**Gate test:** `e2e/phase6.shell.spec.ts` — **7 passed / 1 skipped** (review
console is desktop-only). Hero headline composes (last span opacity→1), journey
loop runs, reduced-motion collapses cleanly, both notification variants render,
review console sorts HIGH-first and an override mutates the row.
**Lighthouse (prod) `/` = 96.**
**Screenshots:** `frontend/e2e/__screenshots__/phase6-hero-*.png`,
`…/phase6-notifications-*.png`, `…/phase6-review.png`.

**Blocked on morning endpoints:** review rows are live once `NEXT_PUBLIC_REVIEW_LIVE=true` (G2).

---

## Phase 7 — Demo hardening ✅ GREEN

**Built / fixed:**
- Killed the reveal's blocking `window.alert()` on **List** — it now routes to
  `/market` (both the standalone reveal and the Returns Desk hand-off), so the
  demo path flows hero→…→marketplace without a modal stop.
- `DEMO_SCRIPT.md` at repo root: the single scripted path (hero → Returns capture
  → grade reveal → list → routed match → marketplace → Health Card → reserve →
  3D scan → review console), seeded identical every run.
- Determinism: fixed seeds across grade/defects/buyers/distances/priorities;
  per-item match flavour is deterministic; reduced-motion clean on every screen;
  retake / error / empty states all reachable on demand.

**Gate test:** `e2e/phase7.e2e.spec.ts` — the full demo path headless, **run
×5 consecutively → 5/5 green, zero console errors** (the spec fails on any
`console.error`/`pageerror`). Full suite re-run on the prod build: **33 passed /
11 skipped** (all skips desktop-only by design). Clean `npm run build`.
**Lighthouse (prod): `/` = 96, `/market` = 96** (both ≥ 90).
**Screenshot:** `frontend/e2e/__screenshots__/phase7-demo-end.png`.

**Blocked on morning endpoints:** none — demo runs fully on mocks; flip flags
per FOR_BACKEND.md to demo on live data.

---

## Night 2 — final summary

- **Full suite (prod build): 33 passed / 11 skipped, 0 failed.** Skips are all
  intentional desktop-only (mobile-3D, mobile-amber-audit, mobile-review,
  mobile-phase7). Phase 7 demo path: **5/5 consecutive, 0 console errors.**
- **Amber audit: clean across all 9 routes** (`/`, `/styleguide`, `/returns`,
  `/reveal`, `/scanner`, `/market`, `/card/[id]`, `/notifications`, `/review`).
- **Lighthouse (prod): `/` = 96 · `/market` = 96.** (Re-run any time:
  `cd frontend && npm run build && npm run start &` then
  `node lh-runner.mjs http://localhost:3000/ http://localhost:3000/market`.)
- **Capability honesty:** scanner = WebGL2 (WebGPU-capable badge); no UI claim
  contradicts devtools.

### Flip-to-live table (every service)
| Flag (default false) | Service / endpoint | Screens it makes live |
|---|---|---|
| `NEXT_PUBLIC_ITEMS_LIVE` | items: create/presign/grade/poll/route/listings + cards verify (+ Health Card composition) | Returns Desk, Reveal, Health Card |
| `NEXT_PUBLIC_MATCHING_LIVE` | G1 `GET /items/{id}/matches` | Reveal "N buyers", marketplace intent, match-push |
| `NEXT_PUBLIC_MARKETPLACE_LIVE` | G3/G4 `GET /marketplace` (grade/distance/price_new) | Marketplace |
| `NEXT_PUBLIC_REVIEW_LIVE` | G2 `GET /review/queue` + `POST /review/{id}` | Review console |
| Cognito env (`NEXT_PUBLIC_COGNITO_*`) | G8 real auth (else dev mock token) | all private routes |

---

# Flow wiring — gallery → connected MVP

Turned the four-phase **showcase** into one **product**: a single seeded item
(`itm_demo` = the deterministic spine id) threads every screen, the hero forks
are gone, and each spine screen advances the story with a persistent progress rail
(Capture → Grade → Route → Buyer → Reserved). No new screens, no restyle.

**What changed:**
- **Hero — one way in.** Single primary CTA "Watch it find its next owner" →
  `/returns`. "See the economics" is now a secondary that scrolls to a static
  economics strip **on the landing** (never deep-links mid-flow). Hero resets the
  journey store on entry for an identical run.
- **One shared demo item, threaded.** New `lib/demo.ts`: `DEMO_ITEM_ID` + a tiny
  `journey` store (sessionStorage-backed, `useJourney`) holding item id + beat +
  listed/reserved. `createItem` gained an optional `item_id` (mock honours it; live
  ignores) so the graded item IS the marketplace top match IS the Health Card
  subject. The matching engine already pins that id as the routed match.
- **Scanner folded into the grade moment (default).** `/returns` → Grade →
  `/scanner?item=…` (amber sweep + the real poll) → auto-advances to
  `/reveal?item=…` on grade-land. RETAKE surfaces on the scanner with a bounce
  back to capture. `/scanner` with no `?item` stays the standalone showcase.
- **Routing moment + guided advance.** Reveal **List** → `/notifications?flow=1`
  (seller→buyer beat) → **Follow it to the buyer** → `/market` → pinned match →
  `/card` → **Reserve** → a 🌱 confirmation → **Run it again** back to hero. Every
  spine screen carries a forward affordance; no dead ends.
- **Review** stays a side branch off the hero nav ("how we keep grades honest").

**New gate:** `e2e/flow.golden-path.spec.ts` — clicks the entire spine and
asserts the **same item id** appears at the reveal, as the `match-push` href, and
as the Health Card's QR value; fails on any console error or context break.
**Run ×5 consecutive → 5/5 green, 0 console errors.** (Replaces the old
`phase7.e2e.spec.ts`.) Existing gates updated to the folded flow (phase2 now
asserts returns→scanner→reveal; phase5 asserts the reserve→confirmation beat).

**Full suite (prod build): 35 passed / 13 skipped, 0 failed** (skips all
desktop-only by design). **Amber audit clean across all 9 routes.**
**Lighthouse (prod): `/` = 100 · `/market` = 100.** Clean `npm run build`.
**Screenshots:** `frontend/e2e/__screenshots__/golden-1-hero … golden-8-confirmation.png`.

**Blocked on morning endpoints:** none. NOTE: the deterministic `itm_demo`
threading is a demo/mock construct; in live mode the backend assigns the id, so
the marketplace "pinned same item" needs the backend to actually list+match that
id (documented in FOR_BACKEND.md).
