"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import gsap from "gsap";
import { Button } from "@/components/ui/button";
import { JourneyLoop } from "@/components/hero/journey-loop";
import { Receipt } from "@/components/ui/receipt";
import { prefersReducedMotion } from "@/lib/motion";
import { journey } from "@/lib/demo";

const LINES = ["Every product", "finds its", "next owner."];

const NAV = [
  { href: "/returns", label: "Returns Desk" },
  { href: "/reveal", label: "Grading reveal" },
  { href: "/scanner", label: "3D scanner" },
  { href: "/market", label: "Marketplace" },
  { href: "/review", label: "Review console" },
  { href: "/styleguide", label: "Styleguide" },
];

export default function Home() {
  const headlineRef = useRef<HTMLHeadingElement>(null);

  // The hero is the one way in — reset the journey for a clean, identical run.
  useEffect(() => {
    journey.reset();
  }, []);

  useEffect(() => {
    const el = headlineRef.current;
    if (!el) return;
    const spans = el.querySelectorAll("[data-line] > span");
    if (prefersReducedMotion()) {
      gsap.set(spans, { yPercent: 0, opacity: 1 });
      return;
    }
    const tl = gsap.fromTo(
      spans,
      { yPercent: 110, opacity: 0 },
      { yPercent: 0, opacity: 1, duration: 0.9, ease: "power3.out", stagger: 0.11 },
    );
    return () => {
      tl.kill();
    };
  }, []);

  return (
    <main className="relative min-h-screen overflow-hidden bg-canvas-warm px-6 py-16">
      <div className="pointer-events-none absolute right-[-6%] top-[8%] select-none font-display text-[clamp(140px,26vw,360px)] font-black uppercase leading-[0.8] tracking-[-0.05em] text-ink/[0.03]">
        RE·USE
      </div>

      <div className="relative mx-auto max-w-[1080px]">
        <div className="font-mono text-[12px] font-bold uppercase tracking-[0.24em] text-amber-deep">
          ReBridge · HackOn with Amazon S6
        </div>

        <h1
          ref={headlineRef}
          data-testid="hero-headline"
          className="mt-5 max-w-[15ch] font-display text-[clamp(44px,9vw,104px)] font-black uppercase leading-[0.92] tracking-[-0.035em]"
        >
          {LINES.map((line, i) => (
            <span key={i} data-line className="block overflow-hidden">
              <span className="block">
                {i === 2 ? (
                  <>
                    next <span className="text-amber-deep">owner.</span>
                  </>
                ) : (
                  line
                )}
              </span>
            </span>
          ))}
        </h1>

        <p className="mt-6 max-w-[54ch] text-[16px] leading-relaxed text-ash">
          A ₹3 AI inspection, a verifiable Product Health Card, and an agent that
          routes every returned product to resale, a neighbour, refurb, or
          donation — in seconds.
        </p>

        {/* One way in. The secondary only scrolls to the economics strip below. */}
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/returns" data-testid="start-journey">
            <Button variant="primary" size="lg">
              Watch it find its next owner →
            </Button>
          </Link>
          <a href="#economics">
            <Button variant="secondary" size="lg">
              See the economics
            </Button>
          </a>
        </div>

        <div className="mt-12 max-w-[760px]">
          <JourneyLoop />
        </div>

        {/* stat ticker */}
        <div className="mt-8 overflow-hidden border-y border-hair py-3">
          <div className="ticker-track flex whitespace-nowrap font-mono text-[12px] text-mute">
            {[0, 1].map((k) => (
              <span key={k} className="flex shrink-0">
                <Stat>
                  <b className="tnum text-ink">15–20%</b> of Indian e-commerce
                  orders are returned
                </Stat>
                <Stat>
                  one return can cost <b className="tnum text-ink">1.5×</b> the
                  delivery charge
                </Stat>
                <Stat>
                  recommerce passes <b className="tnum text-ink">$350B</b> by 2030
                </Stat>
                <Stat>
                  ReBridge grades for <b className="tnum text-amber-deep">₹3</b> in{" "}
                  <b className="tnum text-ink">2 seconds</b>
                </Stat>
              </span>
            ))}
          </div>
        </div>

        {/* economics strip — the secondary CTA target (stays on the landing) */}
        <section
          id="economics"
          data-testid="economics-strip"
          className="mt-16 scroll-mt-8 rounded-card border border-hair bg-paper p-6 shadow-sm sm:p-8"
        >
          <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
            The unit economics
          </div>
          <h2 className="mt-2 font-display text-[28px] font-extrabold uppercase tracking-tight">
            ₹3 in. ₹230 back.
          </h2>
          <p className="mt-2 max-w-[60ch] text-[14px] leading-relaxed text-ash">
            Every routed return is a margin decision, not a write-off. The same
            receipt the operator sees on each item:
          </p>
          <div className="mt-5 max-w-[360px]">
            <Receipt
              rows={[
                { kind: "line", label: "Resale value · Good", value: "₹340" },
                { kind: "line", label: "AI grade ₹3 + pickup", value: "−₹110", muted: true },
                { kind: "rule" },
                { kind: "total", label: "Margin", value: "+₹230" },
                { kind: "line", label: "vs liquidation", value: "−₹15", muted: true },
                { kind: "route", label: "Route", value: "P2P · 3 buyers < 5 km" },
              ]}
            />
          </div>
        </section>

        {/* persistent nav — enrichment + the review side-branch */}
        <nav className="mt-10 flex flex-wrap gap-x-5 gap-y-2 font-sans text-[13px] font-semibold text-mute">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="hover:text-ink">
              {n.label} →
            </Link>
          ))}
        </nav>
      </div>
    </main>
  );
}

function Stat({ children }: { children: React.ReactNode }) {
  return (
    <span className="mx-6 flex items-center gap-1.5">
      <span className="text-amber-deep">—</span>
      {children}
    </span>
  );
}
