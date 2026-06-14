"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import { prefersReducedMotion } from "@/lib/motion";

/**
 * The wordless "journey" loop on a dark editorial stage: a returned item travels
 * → through an amber scan gate → flips to GOOD · ₹340 → arrives at a 🌱 new-owner
 * node. The product moment lives on the dark stage (per the rules); amber only on
 * the scan gate (dark-stage exception) and the ₹ price. Reduced-motion shows the
 * composed end state.
 */
export function JourneyLoop() {
  const stageRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [graded, setGraded] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setGraded(true);
      if (cardRef.current) gsap.set(cardRef.current, { left: "72%" });
      return;
    }
    const card = cardRef.current;
    if (!card) return;
    const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.6 });
    tl.set(card, { left: "6%" })
      .call(() => setGraded(false))
      .to(card, { left: "44%", duration: 1.1, ease: "power1.inOut" })
      .call(() => setGraded(true), [], "+=0.15")
      .to(card, { left: "72%", duration: 1.1, ease: "power1.inOut" }, "+=0.25")
      .to(card, { opacity: 1, duration: 0.6 })
      .to(card, { opacity: 0.25, duration: 0.5 }, "+=0.5");
    return () => {
      tl.kill();
    };
  }, []);

  return (
    <div
      ref={stageRef}
      data-testid="journey-loop"
      className="relative h-[150px] overflow-hidden rounded-card border border-white/10 bg-stage-dark"
    >
      {/* amber scan gate */}
      <div
        className="absolute bottom-6 left-1/2 top-6 w-[2px] -translate-x-1/2"
        style={{
          background: "#FF9900",
          boxShadow: "0 0 18px 3px rgba(255,153,0,.7)",
        }}
      />
      <div className="absolute left-1/2 top-3 -translate-x-1/2 font-mono text-[9px] uppercase tracking-[0.2em] text-amber/70">
        ₹3 scan
      </div>

      {/* owner node */}
      <div className="absolute right-[8%] top-1/2 grid -translate-y-1/2 place-items-center">
        <div className="grid h-12 w-12 place-items-center rounded-full bg-[#15301f] text-[22px] ring-1 ring-[#1EAA52]/40">
          🌱
        </div>
        <span className="mt-1 font-mono text-[9px] uppercase tracking-wider text-[#A9CBB5]">
          new owner
        </span>
      </div>

      {/* travelling card */}
      <div
        ref={cardRef}
        className="absolute top-1/2 flex -translate-y-1/2 items-center gap-2 rounded-xl bg-white/95 px-2.5 py-2 shadow-md"
        style={{ left: "6%" }}
      >
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-[#1a1a1d]">
          <ProductGlyph kind="shoe" className="w-[80%]" />
        </div>
        {graded ? (
          <div className="flex items-center gap-1.5 pr-1" data-testid="journey-graded">
            <GradeBadge grade="Good" size="sm" />
            <Price value="340.00" size="sm" />
          </div>
        ) : (
          <span className="pr-1 font-mono text-[10px] text-mute">returned</span>
        )}
      </div>
    </div>
  );
}
