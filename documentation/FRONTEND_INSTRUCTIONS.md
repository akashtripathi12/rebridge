# ReBridge — Frontend Build Handoff for Claude Code

**You are Claude Code.** You will build the ReBridge frontend. The backend is already written (by a teammate) and **cloned locally** — you do not have its context yet, so **Phase 0 is mandatory: you read the backend and prove you understand it before writing a single line of frontend code.**

**Product in one line:** ReBridge gives every returned / unused / outgrown product its *next best owner* — two AI engines, one **grades** the product from photos, one **matches** it to the right buyer.

**Why this matters:** this is for HackOn with Amazon S6. **Judges notice UI/UX first.** This frontend is a scoring weapon. Build the three "wow" moments to perfection; keep everything else calm, fast, correct.

---

## Operating rules (read once, obey throughout)

1. **Never invent the API.** Every endpoint, field name, enum value, and auth header must come from the actual backend code you read in Phase 0. If something is missing or unclear, **stop and ask** — do not guess a shape.
2. **Phase gates are hard.** Do not start a phase until the previous phase's tests pass and you've shown me the result. Each phase ends with a test + a short report.
3. **Mock-first, then wire.** Build each screen against a typed mock that matches the real contract, get it rendering, then swap to the live API. A screen is never blocked on the backend.
4. **The design is already decided.** Two approved visual references exist (see Design Sources). Match them. Do not invent a new look.
5. **Amber is sacred:** `#FF9900` appears only on the primary action button and the grade badge. Nowhere else.
6. **Numbers are always mono** (JetBrains Mono). The economics are the brand.
7. Respect `prefers-reduced-motion` everywhere. Keyboard-accessible. AA contrast.

---

## PHASE 0 — Understand the backend (no frontend code yet)

**Goal:** produce a written, accurate map of the backend so the frontend integrates correctly on the first try.

**Do this:**
1. Read these in the backend repo, in order: `README.md`, `CLAUDE.md`, then the app entrypoint (e.g. `main.py` / `app/main.py`), then routers/controllers, schemas/models (Pydantic), services, and any `docker-compose`, `.env.example`, or settings file.
2. The architecture was recently changed to a **3-layer architecture** — identify the three layers from the code (likely a routing/API layer → service/business layer → data/repository layer, but **confirm from the actual code**, don't assume). Note how they're separated and where the AI engines (grading, matching/routing) live.
3. Run the backend locally if possible (follow the README). Hit the health endpoint and one real endpoint. If it exposes OpenAPI/Swagger (`/docs`, `/openapi.json`), capture it — that's the source of truth for the contract.

**Produce `BACKEND_MAP.md` in the frontend repo containing:**
- The 3 layers, named as the code names them, with a one-line responsibility each.
- **Full endpoint inventory:** method, path, purpose, auth required?, request schema, response schema (exact field names + types + enum values). Especially nail down: item create, photo upload (presigned? multipart?), grade trigger + grade result, Health Card, routing/decision, **matching/buyer results**, marketplace/listings, review queue.
- **Auth flow:** what the frontend must send (JWT? Cognito? header name? login endpoint?).
- **Async model:** is grading synchronous (response returns the grade) or asynchronous (returns a job id → poll/websocket)? This decides how the UI waits. Confirm from code.
- **Enums verbatim:** the grade values (e.g. Like New / Very Good / Good / Acceptable / Unsellable — but use whatever the backend actually defines), routing decision values, statuses.
- **Env/config** the frontend needs (base URL, region, any keys that belong client-side — and explicitly which keys must NOT be in the frontend).
- A list of **gaps/questions** for me.

**🚦 GATE 0 — STOP.** Post `BACKEND_MAP.md` and your open questions. **Wait for my confirmation** that the contract is right before Phase 1. Getting this wrong poisons every later phase.

---

## Design Sources (the visual truth — match these)

Two HTML files are provided alongside this handoff (the **v2 Premium Retail** skin — this is the approved look). Open and study them; they are pixel-intent:
- **`rebridge_ui_v2.html`** — the **grading reveal** + the **Product Health Card** (fully animated, dark editorial product stage).
- **`rebridge_design_reference_v2.html`** — the **hero**, the full **v2 token system**, and the remaining screens (Rahul camera flow, buyer marketplace, notification, review console) + the 3D/Higgsfield mount-point guidance.

(Earlier `rebridge_ui_direction.html` / `rebridge_design_reference.html` are superseded — use the **v2** files.)

If a styling decision isn't covered, default to: **calmer, fewer, amber-only-for-action**, and cross-check against the `design-md-library` and `ui-ux-pro-max` skills.

---

## Tech stack (decided — do not change)

Next.js 14 (App Router) + TypeScript · Tailwind · shadcn/ui (restyled to tokens, never default look) · **Three.js via @react-three/fiber + @react-three/drei** · GSAP (+ ScrollTrigger) · lucide-react · TanStack Query for server state · Zod for runtime-validating API responses against the Phase-0 contract.

## Skills — what to invoke and when (all installed)

| Skill (trigger) | What it actually gives you | Use it in |
|---|---|---|
| **`ui-ux-pro-max`** | 50+ styles, 161 color palettes, 57 font pairings, 99 UX guidelines, 25 chart types across 10 stacks incl. Next/Tailwind/shadcn; shadcn/ui MCP for component search | Every UI decision — invoke at the start of Phases 1, 3, 5, 6 to validate layout, spacing, interaction states |
| **`ckm:ui-styling`** | shadcn/ui + Radix + Tailwind implementation patterns, accessible components, dark mode | Phase 1 component build; any new shadcn component |
| **`ckm:design-system`** | 3-layer token architecture (primitive→semantic→component), CSS-var scales, component specs | Phase 1 — wiring our tokens into a proper token system |
| **`ckm:brand`** | Brand voice, consistency checklists, messaging | Microcopy + the consistency audit before each gate |
| **`awesome-design-md`** (design-md library) | **74 real brand DESIGN.md files** with exact tokens/type/motion — including `nike`, `stripe`, `linear.app`, `vercel`, `shopify`, `coinbase` | Cross-reference for craft. **Study `nike` (product-hero energy) + `linear.app` (dark, precise UI density) + `stripe` (trust/receipt treatment) and borrow the rigor — NOT their colors.** |
| **`webgpu-threejs-tsl`** | WebGPU / Three.js TSL shader patterns | Phase 4 — the scan shader + WebGL fallback |
| **`playwright-cli`** | Snapshot/ref browser automation: `playwright-cli open/goto/click/type/screenshot`; request-mocking, video-recording, spec-driven-testing references | **The test gate at the end of every phase** + the final demo recording |

**Rule on the design-md library:** it is a *reference for craft*, not a palette source. Our amber/ink/trust tokens (below) are fixed and override everything. Pull **structural discipline** from `linear.app`, **product-hero energy** from `nike`, and **trust/economics treatment** from `stripe`. Never copy another brand's colors over ours.

---

## Design tokens (v2 — Premium Retail · put in `tailwind.config.ts` + CSS vars in Phase 1)

```
/* Warm premium retail: Nike editorial discipline + Apple pearl warmth */
--ink:#111111  --charcoal:#39393b  --ash:#4b4b4d  --mute:#707072  --stone:#9e9ea0
--hair:#E5E5E5  --hair-soft:#EFEAE4
--canvas:#F4F1EC   /* warm parchment — app background (NOT cold grey) */
--paper:#FBFAF7    /* card */    --pearl:#FEFDFB
--amber:#FF9900  --amber-deep:#D97A00   /* PRICE + ACTION ONLY */
--trust:#007D48  --trust-bright:#1EAA52
--sale:#D30005     /* sale/defect, sparingly */

font-display: 'Archivo' 600–900  — headlines & grade badges, UPPERCASE, -0.02em tracking
font-sans:    'Manrope' 400–800  — titles, body, buttons
font-mono:    'JetBrains Mono'   — ALL numbers, prices, IDs, the receipt

radius: card 18 · pill 999 · input 14
shadow: warm & layered — sm: 0 2px 8px rgba(17,17,17,.04); md: 0 8px 24px rgba(17,17,17,.08); lg: 0 30px 60px rgba(17,17,17,.16)
motion: micro 150ms ease-out (-2px) · base 300ms ease · pop 400ms cubic-bezier(.2,1.3,.35,1) · reveal ~4.5s staged
```

**The rules that define the v2 look (do not violate):**
1. **Chrome is black & near-monochrome.** The primary action button is confident **black** (not amber). Amber is reserved for **the price number** + nothing else; green only for trust/verified/margin. The rupee figure should be the brightest thing on every screen.
2. **Products live on a dark editorial stage** (radial charcoal → near-black) with a giant ghosted wordmark behind them — Nike photography-first energy. This is also where the **3D scanner** and **Higgsfield shots** mount.
3. **Headlines & grade badges are uppercase Archivo**, tight tracking, against quiet Manrope body — extreme typographic contrast is what makes it premium, not plain.
4. **Warm parchment canvas + pearl cards**, never clinical grey. Keep editorial edges (radius 18, not pill-soft everything).
5. **Numbers always mono.** Distance replaces star ratings in the marketplace.

---

## The three "wow" moments (80% of polish budget)

1. **3D scannable product** (Phase 4) — orbit a real sneaker, hit *Grade*, an amber scan sweeps the mesh, defect hotspots light up *on the model*. TSL shader, WebGPU renderer + **WebGL fallback**. No other team has this.
2. **The grading reveal** (Phase 3) — model latency as theatre: staged status lines → defect pins → grade stamp → confidence counts up → economics print like a receipt.
3. **The hero** (Phase 6) — Amazon-scale landing: GSAP type reveal + the wordless "journey" loop.

---

## PHASED BUILD PLAN

Each phase: build → **test with `playwright-cli`** → short report → my OK → next. Mock-first within each phase, then wire to the Phase-0 contract.

**How to run every gate (playwright-cli pattern):** `playwright-cli open` → `goto` the route → drive it with `click`/`type`/`press` using refs from the snapshot → `screenshot` each key state → for flows, use **video-recording** to capture the run, and **request-mocking** to stand in for any endpoint not yet live. Write the durable checks as Playwright specs (`spec-driven-testing` reference) so they re-run each phase and catch regressions. A gate is GREEN only when its spec passes headless.

### PHASE 1 — Foundation & design system
**Build:** Next.js + TS scaffold; Tailwind config with all tokens; fonts; shadcn installed and **restyled to tokens**; API client layer (base URL from env, auth header from Phase 0, TanStack Query, Zod schemas mirroring the BACKEND_MAP contract); a typed mock layer; core components: `Button`, `GradeBadge`, `ConfidenceMeter`, `Receipt`, `MatchChip`, `PriorityTag`, `StatusLine`, `PhoneFrame`, `StatChip`.
**Test (gate 1):** playwright loads the app; a `/styleguide` route renders every core component in all states; tokens verified (grep: amber only on Button-primary + GradeBadge); fonts load; mobile (390px) + desktop clean.
**Report:** screenshot of the styleguide. 🚦 Wait for OK.

### PHASE 2 — Returns Desk + live grade integration
**Build:** Returns Desk screen (order context chips, photo capture area, batch strip). Wire **real photo upload + grade** per Phase-0 contract (handle sync vs async correctly — poll/WS if async). Real loading/error/retake states.
**Test (gate 2):** playwright uploads a test image → receives a grade from the **real backend** (or a contract-accurate mock if backend not runnable) → renders grade + confidence; error path shows retake; async polling resolves.
**Report:** screen recording of a real grade round-trip. 🚦 Wait for OK.

### PHASE 3 — The Grading Reveal (theatre)
**Build:** the staged reveal exactly as `rebridge_ui_v2.html` — scanning line, staged status copy, defect pins pop, GOOD stamp, confidence counts up, the **receipt** prints row-by-row in mono (resale → costs → margin → vs liquidation → **Route: P2P · N buyers < 5 km**), amber **List** enables only at the end. Drive it with one GSAP timeline (~4.5s). Reduced-motion collapses to final state.
**Test (gate 3):** playwright triggers a grade → asserts the full sequence renders in order, receipt rows present, List disabled-until-complete; reduced-motion path verified.
**Report:** recording at 1×. 🚦 Wait for OK.

### PHASE 4 — 3D Scannable Product (the centerpiece)
**Build:** `<ProductScanner>` (r3f + drei). Dark studio, key + amber rim light, contact shadow. Load GLB sneaker (asset slot; **procedural placeholder fallback** if absent). OrbitControls (idle auto-rotate). **TSL scan shader:** uniform `uScanY` animated 0→1 by GSAP on *Grade*, emissive amber band sweeps up the mesh + Fresnel rim. **Defect hotspots:** 2–3 drei `<Html>` markers pinned to model coords, pop in as the scan passes, expandable labels. Then GOOD badge + confidence count-up. *Replay scan* control. WebGPU renderer with **automatic WebGL fallback**; lazy-load (`ssr:false`); `frameloop="demand"`; budget <4 MB, 60fps.
**Test (gate 4):** playwright — canvas mounts, auto-rotates, *Grade* runs the sweep, ≥2 hotspots appear, badge+confidence render; **re-run with WebGPU disabled** → WebGL fallback works, no black canvas; offscreen pauses render.
**Report:** recording of scan + the fallback run. 🚦 Wait for OK.

### PHASE 5 — Rahul flow + Buyer marketplace + Health Card
**Build:**
- **Health Card** (`rebridge_ui_v2.html`) — boarding-pass artifact: perforated edge, verified tick, findings (bad/warn/ok), QR + verify affordance, price vs new. Wire to real card/verify endpoint.
- **Rahul capture** — full-screen viewfinder, 3-shot checklist, live hint, **stopwatch chip**.
- **Rahul decision** — single card (grade, confidence, price vs new, **match chip from the real matching endpoint**, pickup slot), one amber **List it — done**; stopwatch ≤ 60s.
- **Buyer marketplace** — tiles lead with grade + **distance (no star ratings)**; the **proactive match push** card; PDP Second-Chance shelf variant. Wire to real listings + matching results.
**Test (gate 5):** playwright — Rahul flow completes ≤60s with one amber action; Health Card has QR+findings+price; marketplace tiles show grade+distance and a match push renders; all data from real endpoints (or contract mocks).
**Report:** recordings of all three. 🚦 Wait for OK.

### PHASE 6 — Hero + Notification + Review Console + polish
**Build:**
- **Hero** (`rebridge_design_reference_v2.html`) — GSAP masked type reveal, the **journey loop** (card travels → amber scan gate → flips to GOOD·₹340 → 🌱 owner node), stat ticker, optional Higgsfield video slot (opacity .25, decoration only).
- **Notification** — leaf ring, "Your shoes found a new owner", CO₂e chip (the screenshot frame).
- **Review Console** (desktop) — queue sorted by value × uncertainty, confirm/override, wired to the review endpoint.
- Global polish: empty/error/loading states, focus rings, 404, metadata.
**Test (gate 6):** playwright full demo walkthrough across all screens capturing submission screenshots; Lighthouse perf ≥ 85 on hero; amber-only audit passes build-wide; reduced-motion + mobile + desktop all clean.
**Report:** the full screenshot set + Lighthouse. 🚦 Wait for OK.

### PHASE 7 — Demo hardening
**Build:** seed realistic demo data; harden the exact live-demo path; pre-warm/handle cold starts; a `Replay` on the scan and reveal; verify on the demo laptop/browser. Layer in Higgsfield assets if available.
**Test (gate 7):** run the end-to-end demo script 5× in playwright with zero failures; record the final 3-minute happy path.
**Report:** the 5 clean runs. 🚦 Done.

---

## Asset slots (build complete without them; they drop in)
| Slot | Where | Spec |
|---|---|---|
| GLB sneaker | `<ProductScanner>` | textured single object; procedural fallback if absent |
| `hero-loop.mp4` | behind hero grid | muted loop, darkened 75%, 6–8s, <6 MB |
| `demo-opener.mp4` | demo video intro | 600km→4km cinematic map shot |

Prompts live in Section 04 of `rebridge_design_reference_v2.html`. If an asset isn't ready at build-freeze, ship the fallback.

---

## Do / Don't
**Do:** one amber action per screen · receipts in mono · staged status copy during AI work · confidence always visible · distance over seller identity · honest microcopy ("We're 76% sure — a human double-checks").
**Don't:** orange headers/icons · star ratings · wordless spinners · dark patterns/fake urgency · stock lifestyle photos · default shadcn look · GSAP/3D inside operator tools · **inventing API shapes** · skipping a test gate.

---

## Definition of done
All 7 gates green; the demo flow runs end-to-end against the real backend; submission screenshots + a 3-min recording captured; `BACKEND_MAP.md` accurate; amber-only and mono-numbers audits pass; reduced-motion, mobile, and desktop all clean.

**Start with Phase 0. Read the backend. Produce `BACKEND_MAP.md`. Then stop and wait for my confirmation.**
