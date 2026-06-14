"use client";

import { Button } from "@/components/ui/button";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Receipt } from "@/components/ui/receipt";
import { MatchChip } from "@/components/ui/match-chip";
import { PriorityTag } from "@/components/ui/priority-tag";
import { StatusLine } from "@/components/ui/status-line";
import { StatChip } from "@/components/ui/stat-chip";
import { PhoneFrame } from "@/components/ui/phone-frame";
import { DarkStage } from "@/components/ui/dark-stage";
import { ProductGlyph } from "@/components/product-glyph";
import { GRADES } from "@/lib/config";

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="mb-12">
      <h2 className="mb-4 font-display text-[15px] font-bold uppercase tracking-[0.12em] text-stone">
        {title}
      </h2>
      <div className="rounded-card border border-hair bg-paper p-6 shadow-sm">
        {children}
      </div>
    </section>
  );
}

export default function StyleguidePage() {
  return (
    <main className="mx-auto max-w-[1080px] px-5 py-12">
      <div className="mb-10">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · v2 · Premium Retail
        </div>
        <h1 className="mt-2 font-display text-[44px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          Component styleguide
        </h1>
        <p className="mt-2 max-w-[60ch] text-[14px] leading-relaxed text-ash">
          The core kit, every state. Amber lives only on the price number; the
          primary action is black; grade badges are black; numbers are mono.
        </p>
      </div>

      <Section id="buttons" title="Buttons & chips">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary">List it — done</Button>
          <Button variant="secondary">Override</Button>
          <Button variant="ghost">Edit price or details</Button>
          <Button variant="idle" disabled>
            List for ₹340
          </Button>
          <Button variant="primary" size="block" className="max-w-[260px]">
            Full-width action
          </Button>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <MatchChip count={3} />
          <MatchChip count={1} />
          <PriorityTag priority="HIGH" />
          <PriorityTag priority="MEDIUM" />
          <PriorityTag priority="LOW" />
        </div>
      </Section>

      <Section id="grades" title="Grade badges (all five, black)">
        <div className="flex flex-wrap items-center gap-3">
          {GRADES.map((g) => (
            <GradeBadge key={g} grade={g} />
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <GradeBadge grade="Good" size="sm" />
          <GradeBadge grade="Good" size="md" />
          <GradeBadge grade="Good" size="lg" />
        </div>
      </Section>

      <Section id="numbers" title="Numbers — mono · price in amber">
        <div className="flex flex-wrap items-end gap-8">
          <Price value="340.00" size="sm" />
          <Price value="1450.00" size="md" />
          <Price value="340.00" priceNew="500.00" size="lg" />
          <Price value="1450.00" priceNew="3299.00" size="xl" />
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-6">
          <span className="tnum text-trust">+₹230</span>
          <span className="tnum">91%</span>
          <span className="tnum text-mute">RB-7F3A-91</span>
        </div>
      </Section>

      <Section id="confidence" title="Confidence meter (counts up)">
        <div className="grid max-w-[420px] gap-5">
          <ConfidenceMeter value={0.91} note="human-spot-checked" />
          <ConfidenceMeter value={0.64} note="a human double-checks" />
          <ConfidenceMeter value={0.77} countUp={false} showBar={false} />
        </div>
      </Section>

      <Section id="status" title="Status lines (AI work, no spinners)">
        <div className="grid max-w-[420px] gap-3">
          <StatusLine text="Matching against original listing…" />
          <StatusLine text="Inspecting upper & soles…" />
          <StatusLine text="Graded Good · matches original listing" done />
        </div>
      </Section>

      <Section id="receipt" title="Receipt (disposition economics)">
        <div className="max-w-[340px]">
          <Receipt
            rows={[
              { kind: "line", label: "Resale value · Good", value: "₹340" },
              {
                kind: "line",
                label: "AI grade ₹3 + pickup ₹107",
                value: "−₹110",
                muted: true,
              },
              { kind: "rule" },
              { kind: "total", label: "Margin", value: "+₹230" },
              {
                kind: "line",
                label: "vs liquidation",
                value: "−₹15",
                muted: true,
              },
              { kind: "route", label: "Route", value: "P2P · 3 buyers < 5 km" },
            ]}
          />
        </div>
      </Section>

      <Section id="chips" title="Stat chips & dark stage">
        <div className="flex flex-wrap items-center gap-3">
          <StatChip label="Order" value="AMZ-7F3A" />
          <StatChip label="Pickup" value="Tmrw 10–12" />
          <StatChip label="CO₂e saved" value="0.9 kg" tone="trust" />
        </div>
        <div className="mt-5 max-w-[320px]">
          <DarkStage ghost="RB" className="h-[180px]">
            <ProductGlyph
              kind="shoe"
              className="relative w-[70%] drop-shadow-[0_20px_26px_rgba(0,0,0,0.5)]"
            />
          </DarkStage>
        </div>
      </Section>

      <Section id="phone" title="Phone frame">
        <div className="max-w-[362px]">
          <PhoneFrame where="Returns · Hub BLR-4">
            <div className="px-4 pb-5 pt-2">
              <DarkStage ghost="RB" className="h-[200px]">
                <ProductGlyph kind="shoe" className="relative w-[72%]" />
              </DarkStage>
              <div className="mt-4">
                <StatusLine text="Graded Good · matches original listing" done />
              </div>
            </div>
          </PhoneFrame>
        </div>
      </Section>
    </main>
  );
}
