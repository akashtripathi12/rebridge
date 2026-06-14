# ReBridge — Demo Script (3-minute happy path)

One scripted path, seeded so it runs **identically every time**. Mock data by
default (no backend needed); flip the flags in `FOR_BACKEND.md` to run on live
endpoints.

## Setup
```
cd frontend
npm run build && npm run start      # http://localhost:3000  (or: npm run dev)
```
Demo on a Chromium-based browser, window ≥ 1280×900. For the "honest AI" beat you
can toggle the OS reduced-motion setting — every screen collapses cleanly.

## The path (story beats in **bold**)

1. **`/` — Hero.** "Every product finds its **next owner.**" The headline rises
   in; the journey loop shows a returned item passing a ₹3 scan gate, flipping to
   **GOOD · ₹340**, landing at a 🌱 new-owner node. *One line: a return becomes a
   second life in seconds.* Click **Watch the demo**.

2. **`/returns` — Returns Desk.** Order context chips (mono). Tap **Add photo**
   twice (front + side) — thumbnails fill the batch strip. *"₹3 inspection, no
   forms."* Tap **Grade 2 photos**.
   - *(Optional trust beat:)* tick **Simulate a blurry capture** before grading →
     the flow returns **RETAKE REQUIRED** ("we'd rather be sure than guess").

3. **Grade reveal (in place).** The amber band sweeps the photo; staged status
   copy; defect **pins pop** (toe, sole); the **GOOD** stamp lands; confidence
   **counts up to 91%**; the **receipt prints** row-by-row — resale ₹340, costs
   −₹110, **margin +₹230**, **Route: P2P · 3 buyers < 5 km**. The amber **List
   for ₹340** enables only at the end. Tap it.

4. **`/scanner` — 3D scan (the wow).** *(Navigate here from the hero nav, or show
   between beats 3 and 5.)* Orbit the product on the dark studio stage; hit
   **Grade** — the amber band sweeps the mesh, **defect hotspots** light up on the
   model, then **GOOD + 91%**. Badge reads `WebGL2 · WebGPU-capable` (honest).
   **Replay scan** to repeat.

5. **`/market` — Engine B made visible.** Listing it dropped you here. The
   **proactive match push** leads: *"A graded match near you — routed to you,
   wishlisted these."* Below, the **Second Chance** grid — every tile leads with
   **grade + amber price + distance + % match + intent reason**, never a star
   rating. Filter by category (Books → 1, Nearby → all). Tap the match push.

6. **`/card/itm_shoe7` — the Health Card (trust primitive).** The boarding-pass
   artifact: dark product band, **Verified** tick, **GOOD · 91%**, findings
   (toe/sole), a **real scannable QR** (resolves to this card's URL), HMAC
   signature, **₹340 vs ₹500 — save 32%**. Tap **Reserve** → reserved. *"Anyone
   can verify — no account needed."*

7. **`/notifications` — the loop closes.** Both sides notified: seller *"Your
   shoes found a new owner — routed to 3 buyers < 5 km, 0.9 kg CO₂e saved"*;
   buyer *"A graded match near you."*

8. **`/review` — a human double-checks.** The operator console: low-confidence
   grades sorted by **value × uncertainty** (HIGH first). **Confirm** or
   **Override** a grade (it mutates in place) — *"every override trains the
   model."* This is the honesty beat: the AI defers when unsure.

## Closing line
"Two engines — one grades the product, one finds its buyer — turning returns from
a 600 km reverse-logistics cost into a 4 km second life. Graded for ₹3, in
seconds."

## Determinism notes
- Hero item, grade (GOOD, 91%), defects (toe/sole), buyers (3 < 5 km), prices,
  distances, and review priorities are all seeded constants — identical each run.
- The grade poll is real (~4.2s mock latency); the reveal theatre paces to it.
- Reduced-motion: every animated screen renders its final composed state.
- Reset anything by reloading the route; the demo carries no cross-run state.

## Verify it still runs
```
cd frontend && npx playwright test phase7 --project=desktop --repeat-each=5
```
Expect 5/5 green, zero console errors.
