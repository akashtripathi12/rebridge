"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { DarkStage } from "@/components/ui/dark-stage";
import { ProductGlyph } from "@/components/product-glyph";
import { GradeBadge } from "@/components/ui/grade-badge";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Receipt, type ReceiptRow } from "@/components/ui/receipt";
import { Button } from "@/components/ui/button";
import { StatusLine } from "@/components/ui/status-line";
import { Price } from "@/components/ui/price";
import type { GradeFacet, DecisionFacet } from "@/lib/schemas";
import { formatMoney, formatSignedMoney } from "@/lib/format";
import { prefersReducedMotion } from "@/lib/motion";

const SCANNING_COPY = [
  "Matching against original listing…",
  "Inspecting upper & soles…",
  "Checking completeness…",
];

/** Map a free-text defect to one of two fixed pin spots on the 2D stage (G7). */
function pinFor(location: string): { left: string; top: string } {
  const l = location.toLowerCase();
  if (l.includes("toe") || l.includes("upper") || l.includes("front"))
    return { left: "26%", top: "44%" };
  if (l.includes("sole") || l.includes("heel") || l.includes("bottom"))
    return { left: "58%", top: "70%" };
  return { left: "42%", top: "54%" };
}

export interface RevealResult {
  grade: GradeFacet;
  decision: DecisionFacet | null;
  matchCount: number;
  disposition: string;
}

/**
 * GradingReveal — the centerpiece theatre. While `result` is null it shows the
 * scan sweep + cycling status copy (paced to the REAL grade poll). When the
 * result lands it runs one GSAP timeline: pins pop → grade stamp → confidence
 * counts up → receipt prints row-by-row → amber-priced CTA enables.
 * Reduced-motion collapses straight to the final state.
 */
export function GradingReveal({
  result,
  imageUrl,
  onList,
  productKind = "shoe",
}: {
  result: RevealResult | null;
  imageUrl?: string | null;
  onList?: () => void;
  productKind?: string;
}) {
  const [copyIdx, setCopyIdx] = useState(0);
  const [revealStarted, setRevealStarted] = useState(false);
  const [rowsShown, setRowsShown] = useState(0);
  const [stampShown, setStampShown] = useState(false);
  const [pinsShown, setPinsShown] = useState(0);
  const [ctaReady, setCtaReady] = useState(false);

  const scanRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  const done = result !== null;
  const reduced = prefersReducedMotion();

  // Cycle the scanning copy until the result lands.
  useEffect(() => {
    if (done) return;
    const id = setInterval(
      () => setCopyIdx((i) => Math.min(i + 1, SCANNING_COPY.length - 1)),
      reduced ? 99999 : 950,
    );
    return () => clearInterval(id);
  }, [done, reduced]);

  // Animate the scan line while scanning.
  useEffect(() => {
    if (done || reduced || !scanRef.current) return;
    const tween = gsap.fromTo(
      scanRef.current,
      { top: "-12%", opacity: 0 },
      {
        top: "100%",
        opacity: 1,
        duration: 1.2,
        ease: "none",
        repeat: -1,
        yoyo: false,
      },
    );
    return () => {
      tween.kill();
    };
  }, [done, reduced]);

  // When result lands, run the staged reveal.
  useEffect(() => {
    if (!result) return;
    setRevealStarted(true);
    const defectCount = Math.min(result.grade.defects.length, 2);
    if (reduced) {
      setPinsShown(defectCount);
      setStampShown(true);
      setRowsShown(99);
      setCtaReady(true);
      return;
    }
    const tl = gsap.timeline();
    tl.call(() => setPinsShown(1), [], 0.2)
      .call(() => setPinsShown(defectCount), [], 0.55)
      .call(() => setStampShown(true), [], 0.95)
      .call(() => setRowsShown(99), [], 1.5)
      .call(() => setCtaReady(true), [], 2.6);
    return () => {
      tl.kill();
    };
  }, [result, reduced]);

  const grade = result?.grade;
  const decision = result?.decision;

  const receiptRows: ReceiptRow[] = decision
    ? [
        {
          kind: "line",
          label: `Resale value · ${grade?.grade ?? ""}`,
          value: formatMoney(decision.value),
        },
        {
          kind: "line",
          label: "AI grade + pickup",
          value: formatSignedMoney(`-${decision.cost}`),
          muted: true,
        },
        { kind: "rule" },
        {
          kind: "total",
          label: "Margin",
          value: formatSignedMoney(decision.margin),
        },
        { kind: "line", label: "vs liquidation", value: "−₹15", muted: true },
        {
          kind: "route",
          label: "Route",
          value: `${result?.disposition ?? decision.disposition} · ${result?.matchCount ?? 0} buyers < 5 km`,
        },
      ]
    : [];

  return (
    <div className="flex flex-col gap-3 px-4 pb-5">
      {/* Stage */}
      <div ref={stageRef} className="relative mt-1.5">
        <DarkStage ghost="RB" className="h-[240px]">
          {imageUrl ? (
            // G5: render the locally-captured photo, no GET-presign needed.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl}
              alt="Captured item"
              className="relative h-[78%] w-[78%] object-contain drop-shadow-[0_24px_30px_rgba(0,0,0,0.5)]"
            />
          ) : (
            <ProductGlyph
              kind={productKind}
              className="relative w-[78%] drop-shadow-[0_24px_30px_rgba(0,0,0,0.5)]"
            />
          )}

          {/* Scan sweep (amber — the scanner light, dark stage only) */}
          {!done && (
            <div
              ref={scanRef}
              data-testid="scan-line"
              className="pointer-events-none absolute left-0 right-0 h-[54px]"
              style={{
                background:
                  "linear-gradient(180deg,transparent,rgba(255,153,0,.20),transparent)",
                borderTop: "2px solid rgba(255,153,0,.9)",
                boxShadow: "0 0 30px 6px rgba(255,153,0,.35)",
              }}
            />
          )}

          {/* Defect pins */}
          {grade?.defects.slice(0, 2).map((d, i) => {
            const pos = pinFor(d.location);
            const visible = i < pinsShown;
            return (
              <div
                key={i}
                data-testid="defect-pin"
                className="absolute flex items-center gap-1.5 transition-all duration-[400ms] ease-pop"
                style={{
                  left: pos.left,
                  top: pos.top,
                  opacity: visible ? 1 : 0,
                  transform: visible ? "scale(1)" : "scale(.5)",
                }}
              >
                <div className="grid h-6 w-6 place-items-center rounded-full bg-white font-mono text-[11px] font-bold text-ink shadow-md ring-4 ring-white/25">
                  {i + 1}
                </div>
                <div className="whitespace-nowrap rounded-md bg-white/95 px-2 py-1 font-sans text-[10.5px] font-semibold text-ink shadow-md">
                  {d.severity} · {d.location}
                </div>
              </div>
            );
          })}

          {/* Grade stamp */}
          {grade && (
            <div
              data-testid="grade-stamp"
              className="absolute left-4 top-4 flex items-center gap-2 rounded-pill bg-white/95 py-1.5 pl-2 pr-3.5 shadow-md transition-all duration-[450ms] ease-pop"
              style={{
                opacity: stampShown ? 1 : 0,
                transform: stampShown ? "none" : "translateY(-8px)",
              }}
            >
              <GradeBadge grade={grade.grade} size="sm" />
              <span className="tnum text-[11px] font-semibold text-ash">
                {Math.round(grade.confidence * 100)}% confidence
              </span>
            </div>
          )}
        </DarkStage>
      </div>

      {/* Status line */}
      <StatusLine
        text={
          done
            ? `Graded ${grade?.grade} · matches original listing`
            : SCANNING_COPY[copyIdx]
        }
        done={done}
      />

      {/* Confidence (appears with the stamp) */}
      {grade && stampShown && (
        <ConfidenceMeter
          value={grade.confidence}
          note="a human double-checks low scores"
        />
      )}

      {/* Receipt */}
      {decision && (
        <Receipt rows={receiptRows} revealed={revealStarted ? rowsShown : 0} />
      )}

      {/* Amber-priced CTA — enabled only at the end */}
      <Button
        variant={ctaReady ? "primary" : "idle"}
        size="block"
        disabled={!ctaReady}
        data-testid="list-cta"
        onClick={() => ctaReady && onList?.()}
        className="mt-1"
      >
        List for{" "}
        {decision ? (
          <Price value={decision.price} size="sm" className="ml-1" />
        ) : (
          "—"
        )}
      </Button>
    </div>
  );
}
