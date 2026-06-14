"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Receipt, type ReceiptRow } from "@/components/ui/receipt";
import { ArrowDown, ArrowUp, Leaf, Route, Sparkles } from "lucide-react";
import { prefersReducedMotion } from "@/lib/motion";

const RECEIPT_ROWS: ReceiptRow[] = [
  { kind: "line", label: "Resale value · Good", value: "₹340" },
  { kind: "line", label: "AI grade ₹3 + pickup", value: "−₹110", muted: true },
  { kind: "rule" },
  { kind: "total", label: "Margin", value: "+₹230" },
  { kind: "line", label: "vs liquidation", value: "−₹15", muted: true },
  { kind: "route", label: "Route", value: "P2P · 3 buyers < 5 km" },
];

const COMPARE: { label: string; old: string; rb: string; delta: string }[] = [
  { label: "Distance travelled", old: "600 km", rb: "4 km", delta: "−99%" },
  { label: "Reverse-logistics cost", old: "₹190", rb: "₹107", delta: "−44%" },
  { label: "Time to next owner", old: "14 days", rb: "1 day", delta: "−93%" },
  { label: "Recovered value", old: "₹15", rb: "₹340", delta: "+22×" },
];

const IMPACT: { Icon: React.ComponentType<{ className?: string }>; value: string; label: string }[] = [
  { Icon: Route, value: "596 km", label: "distance avoided per routed return (modelled)" },
  { Icon: Leaf, value: "0.9 kg", label: "CO₂e avoided per neighbour handoff (modelled)" },
  { Icon: Sparkles, value: "+₹230", label: "modelled margin vs. write-off (Good-grade, seeded band)" },
];

/**
 * Economics, in depth. The receipt prints row by row on scroll-into-view; the
 * "before vs ReBridge" table animates the deltas; impact tiles fade up. This is
 * the "more knowledge about economics" section the brief asks for — the unit
 * economics that make the pitch land.
 */
export function EconomicsDeep() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    gsap.registerPlugin(ScrollTrigger);

    const ctx = gsap.context(() => {
      const reduced = prefersReducedMotion();
      const rows = gsap.utils.toArray<HTMLElement>("[data-compare-row]");
      const tiles = gsap.utils.toArray<HTMLElement>("[data-impact-tile]");

      if (reduced) {
        gsap.set([...rows, ...tiles], { opacity: 1, y: 0 });
        return;
      }

      gsap.set(rows, { opacity: 0, x: -20 });
      gsap.set(tiles, { opacity: 0, y: 24 });

      rows.forEach((row, i) => {
        gsap.to(row, {
          opacity: 1,
          x: 0,
          duration: 0.45,
          ease: "power2.out",
          delay: i * 0.07,
          scrollTrigger: { trigger: row, start: "top 85%", once: true },
        });
      });

      tiles.forEach((tile, i) => {
        gsap.to(tile, {
          opacity: 1,
          y: 0,
          duration: 0.5,
          ease: "power2.out",
          delay: i * 0.08,
          scrollTrigger: { trigger: tile, start: "top 85%", once: true },
        });
      });
    }, root);

    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={root}
      id="economics"
      data-testid="economics-deep"
      className="scroll-mt-16 bg-canvas px-4 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto grid max-w-[1200px] gap-12 lg:grid-cols-[minmax(0,440px)_1fr] lg:gap-16">
        <div>
          <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
            The unit economics
          </div>
          <h2 className="mt-3 font-display text-[clamp(28px,5vw,52px)] font-extrabold uppercase leading-[1] tracking-[-0.02em]">
            One inspection. Hundreds back.
          </h2>
          <div className="mt-8 max-w-[360px]">
            <Receipt rows={RECEIPT_ROWS} className="bg-white" />
          </div>
        </div>

        <div className="flex flex-col gap-10">
          {/* Before vs ReBridge comparison */}
          <div>
            <div className="font-sans text-[11px] font-bold uppercase tracking-[0.16em] text-stone">
              Before vs ReBridge
            </div>
            <div
              data-testid="compare-table"
              className="mt-3 overflow-hidden rounded-card border border-hair bg-white"
            >
              <div className="grid grid-cols-[1.4fr_1fr_1fr_auto] gap-3 bg-ink px-4 py-2.5 font-sans text-[10px] font-bold uppercase tracking-[0.14em] text-white">
                <span>What it costs</span>
                <span>Today</span>
                <span>With ReBridge</span>
                <span className="text-right">Δ</span>
              </div>
              {COMPARE.map((row, i) => {
                const better = row.delta.startsWith("+") || row.delta.startsWith("−");
                const positive =
                  row.delta.startsWith("+") || row.delta.startsWith("−9") || row.delta.startsWith("−4") || row.delta.startsWith("−5") || row.delta.startsWith("−6") || row.delta.startsWith("−7") || row.delta.startsWith("−8");
                return (
                  <div
                    key={i}
                    data-compare-row
                    className="grid grid-cols-[1.4fr_1fr_1fr_auto] items-center gap-3 border-b border-hair px-4 py-3 last:border-none"
                  >
                    <span className="text-[13px] font-medium text-ash">
                      {row.label}
                    </span>
                    <span className="tnum text-[13px] text-mute line-through">
                      {row.old}
                    </span>
                    <span className="tnum text-[14px] font-semibold text-ink">
                      {row.rb}
                    </span>
                    <span
                      className={`tnum flex items-center justify-end gap-0.5 text-[12px] font-bold ${
                        better && positive ? "text-trust" : "text-mute"
                      }`}
                    >
                      {row.delta.startsWith("−") ? (
                        <ArrowDown className="h-3 w-3" />
                      ) : (
                        <ArrowUp className="h-3 w-3" />
                      )}
                      {row.delta}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Impact */}
          <div>
            <div className="font-sans text-[11px] font-bold uppercase tracking-[0.16em] text-stone">
              Impact, per routed return
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {IMPACT.map((tile, i) => (
                <div
                  key={i}
                  data-impact-tile
                  className="rounded-card border border-hair bg-white p-5"
                >
                  <tile.Icon className="h-5 w-5 text-amber-deep" />
                  <div className="tnum mt-3 font-display text-[24px] font-extrabold tracking-tight text-ink">
                    {tile.value}
                  </div>
                  <div className="mt-1 text-[12.5px] leading-snug text-ash">
                    {tile.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
