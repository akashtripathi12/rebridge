# ReBridge — Demo Script (the golden path)

**One item, one click, start to finish.** From the hero, a single CTA grades a
real returned item, prices it, routes it, and reserves it for a named nearby
buyer — **the same item the whole way** — with the human-review branch one tap
away. A product you walk, not a deck you click.

Mock data by default (no backend needed); flip the flags in `FOR_BACKEND.md` to
run on live endpoints. The whole spine is seeded → identical every run.

## Setup
```
cd frontend
npm run build && npm run start      # http://localhost:3000  (or: npm run dev)
```
Chromium-based browser, window ≥ 1280×900. A slim **progress rail**
(Capture → Grade → Route → Buyer → Reserved) sits atop every spine screen so you
always see the arc. To show the "honest AI" beat, toggle OS reduced-motion — every
screen collapses cleanly to its final state.

## The spine (one item: `itm_demo`)

1. **`/` Hero.** "Every product finds its **next owner.**" One primary CTA →
   **"Watch it find its next owner."** *(The secondary "See the economics" only
   scrolls to the ₹3-in/₹230-back receipt strip lower on the landing — it never
   deep-links into the flow.)* Click the primary.

2. **`/returns` — Capture (beat 1).** Order context chips (`AMZ-7F3A`, Shoes,
   8 mo). Tap **Add photo** twice → thumbnails fill the strip. Tap **Grade**.
   This creates the one demo item and starts the real `meta.status` poll.

3. **`/scanner?item=… ` — Grade, made visible (beat 2).** The ₹3 inspection as
   theatre: the amber band sweeps the 3D mesh while the poll runs; defect hotspots
   (scuff·toe, wear·sole) light up on the model — the same defects the card shows.
   On grade-land it advances to the verdict (or tap **See the verdict →**).
   *(Badge stays honest: `WebGL2 · WebGPU-capable`.)*

4. **`/reveal?item=… ` — the verdict (beat 2).** GOOD · 91%, defect pins, the
   economics receipt prints — resale ₹340, −₹110, **margin +₹230**, **Route: P2P ·
   3 buyers < 5 km**. The amber **List for ₹340** enables at the end. Tap it.

5. **`/notifications?flow=1` — the routing moment (beat 3).** Both sides notified:
   seller *"Your shoes found a new owner — routed to 3 buyers < 5 km"*; buyer Rahul
   *"a graded match near you."* Tap **Follow it to the buyer →**.

6. **`/market` — Second Chance, as Rahul (beat 4).** The **same item is the pinned
   top match** ("Running Shoes · UK 7 · GOOD · ₹340 · < 4 km · wishlisted these"),
   above the ambient seeded tiles. Distance, not stars. Tap the match.

7. **`/card/itm_demo` — the Health Card (beat 4).** The trust primitive: Verified,
   GOOD · 91%, the same defects, a **real scannable QR** to this card, signature,
   ₹340 vs ₹500 (save 32%). Tap **Reserve**.

8. **Confirmation (beat 5).** "A returned product just started its second life 🌱
   — reserved by a buyer 4 km away." Tap **Run it again →** back to the hero.

### Side branch (one tap, off the spine)
**`/review`** — *"how we keep grades honest."* The operator console: low-confidence
grades sorted by value × uncertainty; **Confirm / Override / Retake**. This is the
trust story behind the card's "Verified" — the human double-check. Reach it from
the hero nav.

## Closing line
"Two engines — one grades the product, one finds its buyer — turning a return from
a 600 km reverse-logistics cost into a 4 km second life. Graded for ₹3, in
seconds."

## Determinism
- One seeded item threads the whole path; grade (GOOD/91%), defects (toe/sole),
  buyers (3 < 5 km), prices, distances, priorities are all fixed constants.
- The grade poll is real (~4.2s mock latency); the scan + reveal pace to it.
- Reduced-motion: every animated screen renders its composed final state.
- The hero resets the journey on entry, so each run is identical. No dead ends —
  every spine screen has a forward affordance + the progress rail.

## Verify it still runs
```
cd frontend && npx playwright test flow.golden-path --project=desktop --repeat-each=5
```
Expect 5/5 green, zero console errors, and the SAME item id asserted at the
reveal, as the pinned top marketplace match, and on the Health Card.
