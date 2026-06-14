"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { DarkStage } from "@/components/ui/dark-stage";
import { ProductGlyph } from "@/components/product-glyph";
import { prefersReducedMotion } from "@/lib/motion";

const STATUSES = [
  "Matching against original listing…",
  "Inspecting upper & soles…",
  "Checking completeness…",
];

/**
 * LiveDemo — an embedded, auto-playing micro-version of the grade reveal,
 * placed inside the landing page (NOT a full-page flow). Triggers when scrolled
 * into view; the amber scan beam sweeps the product, defect pins pop, the grade
 * stamp lands, then the receipt prints. Loops on a long delay so the page never
 * looks dead. Honors reduced-motion.
 */
export function LiveDemo() {
  const root = useRef<HTMLDivElement>(null);
  const scanRef = useRef<HTMLDivElement>(null);
  const [graded, setGraded] = useState(false);
  const [statusIdx, setStatusIdx] = useState(0);
  const [pinsShown, setPinsShown] = useState(0);
  const [receiptRows, setReceiptRows] = useState(0);

  useEffect(() => {
    const reduced = prefersReducedMotion();
    if (reduced) {
      setGraded(true);
      setPinsShown(2);
      setReceiptRows(99);
      return;
    }

    gsap.registerPlugin(ScrollTrigger);
    let tlMaster: gsap.core.Timeline | null = null;
    let scanTween: gsap.core.Tween | null = null;
    let statusInterval: ReturnType<typeof setInterval> | null = null;

    const reset = () => {
      setGraded(false);
      setStatusIdx(0);
      setPinsShown(0);
      setReceiptRows(0);
    };

    const run = () => {
      reset();
      if (scanRef.current) {
        scanTween?.kill();
        scanTween = gsap.fromTo(
          scanRef.current,
          { top: "-15%", opacity: 0 },
          { top: "100%", opacity: 1, duration: 1.2, ease: "none", repeat: 2 },
        );
      }
      statusInterval && clearInterval(statusInterval);
      let i = 0;
      statusInterval = setInterval(() => {
        i = Math.min(i + 1, STATUSES.length - 1);
        setStatusIdx(i);
      }, 1100);

      tlMaster?.kill();
      tlMaster = gsap.timeline({ delay: 3.4 });
      tlMaster
        .call(() => {
          if (statusInterval) clearInterval(statusInterval);
          scanTween?.kill();
          if (scanRef.current) gsap.set(scanRef.current, { opacity: 0 });
        })
        .call(() => setPinsShown(1))
        .call(() => setPinsShown(2), [], "+=0.3")
        .call(() => setGraded(true), [], "+=0.4")
        .call(() => setReceiptRows(99), [], "+=0.4");
    };

    const st = ScrollTrigger.create({
      trigger: root.current,
      start: "top 75%",
      onEnter: run,
    });

    return () => {
      st.kill();
      tlMaster?.kill();
      scanTween?.kill();
      if (statusInterval) clearInterval(statusInterval);
    };
  }, []);

  return (
    <section
      ref={root}
      data-testid="live-demo"
      className="bg-canvas px-4 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          See it live
        </div>
        <h2 className="mt-3 max-w-[20ch] font-display text-[clamp(28px,5vw,52px)] font-extrabold uppercase leading-[1] tracking-[-0.02em]">
          One ₹3 inspection. One verdict. One receipt.
        </h2>
        <p className="mt-4 max-w-[58ch] text-[15px] leading-relaxed text-ash">
          Scroll this into view. The amber scan is the inspection. The pins are
          what the model saw. The receipt is the routing decision the operator
          accepts — or sends to the review queue.
        </p>

        <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,520px)_1fr] lg:gap-10">
          <DarkStage ghost="RB" className="relative aspect-[5/4] w-full">
            <ProductGlyph
              kind="shoe"
              className="relative w-[68%] drop-shadow-[0_24px_30px_rgba(0,0,0,0.5)]"
            />
            {!graded && (
              <div
                ref={scanRef}
                className="pointer-events-none absolute left-0 right-0 h-[60px]"
                style={{
                  background:
                    "linear-gradient(180deg,transparent,rgba(255,153,0,.22),transparent)",
                  borderTop: "2px solid rgba(255,153,0,.9)",
                  boxShadow: "0 0 30px 6px rgba(255,153,0,.35)",
                }}
              />
            )}
            {/* defect pins */}
            <Pin n={1} label="minor scuff · left toe" left="26%" top="44%" show={pinsShown >= 1} />
            <Pin n={2} label="light wear · sole" left="58%" top="70%" show={pinsShown >= 2} />
            {graded && (
              <div className="absolute left-4 top-4 flex items-center gap-2 rounded-pill bg-white/95 py-1.5 pl-2 pr-3.5 shadow-md">
                <GradeBadge grade="Good" size="sm" />
                <span className="tnum text-[11px] font-semibold text-ash">
                  91% confidence
                </span>
              </div>
            )}
          </DarkStage>

          <div className="flex flex-col gap-4">
            <div className="flex min-h-[28px] items-center gap-2.5">
              <span
                className={`h-[7px] w-[7px] rounded-full ${
                  graded ? "bg-trust" : "animate-pulse2 bg-amber"
                }`}
              />
              <span
                className={`font-sans text-[14px] ${
                  graded ? "font-semibold text-trust" : "font-medium text-ash"
                }`}
              >
                {graded ? "Graded Good · matches original listing" : STATUSES[statusIdx]}
              </span>
            </div>

            {/* receipt */}
            <div className="rounded-card border border-hair bg-paper px-4 py-3.5">
              <div className="mb-2 font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
                Disposition economics
              </div>
              <div className="flex flex-col">
                {[
                  { l: "Resale value · Good", v: "₹340", muted: false },
                  { l: "AI grade ₹3 + pickup", v: "−₹110", muted: true },
                ].map((r, i) => (
                  <div
                    key={i}
                    className={`tnum flex justify-between py-1 text-[13px] font-medium transition-all duration-300 ${
                      receiptRows > i ? "opacity-100" : "opacity-0"
                    } ${r.muted ? "text-mute" : "text-ink"}`}
                  >
                    <span className="font-sans font-medium">{r.l}</span>
                    {r.v}
                  </div>
                ))}
                <div
                  className={`my-1 border-t border-dashed border-hair transition-opacity ${
                    receiptRows > 2 ? "opacity-100" : "opacity-0"
                  }`}
                />
                <div
                  className={`tnum flex justify-between py-1 text-[13px] font-semibold transition-all duration-300 ${
                    receiptRows > 3 ? "opacity-100" : "opacity-0"
                  }`}
                >
                  <span className="font-sans">Margin</span>
                  <b className="font-semibold text-trust">+₹230</b>
                </div>
                <div
                  className={`tnum flex justify-between py-1 text-[13px] font-medium text-mute transition-all duration-300 ${
                    receiptRows > 4 ? "opacity-100" : "opacity-0"
                  }`}
                >
                  <span className="font-sans">vs liquidation</span>−₹15
                </div>
                <div
                  className={`tnum flex justify-between py-1 text-[13px] font-semibold transition-all duration-300 ${
                    receiptRows > 5 ? "opacity-100" : "opacity-0"
                  }`}
                >
                  <span className="font-sans">Route</span>
                  <b className="text-amber-deep">P2P · 3 buyers &lt; 5 km</b>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <span className="text-[12px] font-semibold uppercase tracking-wider text-mute">
                List it for
              </span>
              <Price value="340.00" priceNew="500.00" size="xl" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Pin({
  n,
  label,
  left,
  top,
  show,
}: {
  n: number;
  label: string;
  left: string;
  top: string;
  show: boolean;
}) {
  return (
    <div
      className="absolute flex items-center gap-1.5 transition-all duration-[400ms] ease-pop"
      style={{
        left,
        top,
        opacity: show ? 1 : 0,
        transform: show ? "scale(1)" : "scale(.5)",
      }}
    >
      <div className="grid h-6 w-6 place-items-center rounded-full bg-white font-mono text-[11px] font-bold text-ink shadow-md ring-4 ring-white/25">
        {n}
      </div>
      <div className="whitespace-nowrap rounded-md bg-white/95 px-2 py-1 font-sans text-[10.5px] font-semibold text-ink shadow-md">
        {label}
      </div>
    </div>
  );
}
