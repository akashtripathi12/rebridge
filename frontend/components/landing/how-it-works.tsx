"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Camera, ScanLine, ShieldCheck, MapPin, Sprout } from "lucide-react";
import { prefersReducedMotion } from "@/lib/motion";

const STEPS: { Icon: React.ComponentType<{ className?: string }>; title: string; body: string }[] = [
  {
    Icon: Camera,
    title: "Photograph the return",
    body: "Two to four angles on the desk or at home. Order context auto-attaches.",
  },
  {
    Icon: ScanLine,
    title: "AI grades it for ₹3",
    body: "A vision-model cascade inspects the item — Like New through Unsellable — in seconds.",
  },
  {
    Icon: ShieldCheck,
    title: "We issue a Health Card",
    body: "HMAC-signed, QR-verifiable. The buyer can confirm the grade independently.",
  },
  {
    Icon: MapPin,
    title: "Routed to the right next owner",
    body: "Resell, refurb, peer-to-peer, or donate — chosen by unit economics, not gut.",
  },
  {
    Icon: Sprout,
    title: "Second life, not warehouse round-trip",
    body: "On average a 4 km handoff instead of 600 km of reverse logistics.",
  },
];

if (typeof window !== "undefined" && !ScrollTrigger.isTouch) {
  gsap.registerPlugin(ScrollTrigger);
}

/**
 * How it works — the 5-step explainer. GSAP ScrollTrigger reveals each step as
 * you scroll, with an amber thread connecting them. Reduced-motion shows the
 * composed end state. This is the section the brief asks for: "a full user flow
 * listed with proper animation and gsap" on the landing.
 */
export function HowItWorks() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    gsap.registerPlugin(ScrollTrigger);

    const ctx = gsap.context(() => {
      const reduced = prefersReducedMotion();
      const steps = gsap.utils.toArray<HTMLElement>("[data-flow-step]");
      const thread = root.current?.querySelector<HTMLElement>("[data-flow-thread]");

      if (reduced) {
        gsap.set(steps, { opacity: 1, y: 0 });
        if (thread) gsap.set(thread, { scaleY: 1, transformOrigin: "top" });
        return;
      }

      gsap.set(steps, { opacity: 0, y: 40 });

      steps.forEach((step, i) => {
        gsap.to(step, {
          opacity: 1,
          y: 0,
          duration: 0.7,
          ease: "power2.out",
          scrollTrigger: {
            trigger: step,
            start: "top 80%",
            once: true,
          },
          delay: i * 0.04,
        });
      });

      if (thread) {
        gsap.set(thread, { scaleY: 0, transformOrigin: "top" });
        gsap.to(thread, {
          scaleY: 1,
          ease: "none",
          scrollTrigger: {
            trigger: root.current,
            start: "top 70%",
            end: "bottom 30%",
            scrub: 0.6,
          },
        });
      }
    }, root);

    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={root}
      id="how-it-works"
      data-testid="how-it-works"
      className="scroll-mt-16 bg-canvas px-4 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          How it works
        </div>
        <h2 className="mt-3 max-w-[18ch] font-display text-[clamp(28px,5vw,52px)] font-extrabold uppercase leading-[1] tracking-[-0.02em]">
          A returned product, given its next life — in five steps.
        </h2>
        <p className="mt-4 max-w-[60ch] text-[15px] leading-relaxed text-ash">
          Two AI engines: one grades the product from photos, one finds it the
          right buyer. Every step is verifiable.
        </p>

        <div className="relative mt-14 grid gap-10 sm:gap-14">
          {/* amber thread */}
          <div
            data-flow-thread
            className="pointer-events-none absolute left-[26px] top-2 hidden h-[calc(100%-2rem)] w-[2px] bg-gradient-to-b from-amber via-amber to-trust sm:block"
          />

          {STEPS.map((step, i) => (
            <div
              key={i}
              data-flow-step
              className="relative grid gap-4 sm:grid-cols-[56px_1fr] sm:gap-7"
            >
              <div className="relative z-[1] grid h-[56px] w-[56px] flex-none place-items-center rounded-card bg-ink text-white shadow-md">
                <step.Icon className="h-6 w-6 text-amber" />
                <span className="tnum absolute -bottom-1.5 -right-1.5 grid h-5 w-5 place-items-center rounded-full bg-white font-mono text-[10px] font-bold text-ink shadow-sm">
                  {i + 1}
                </span>
              </div>
              <div className="pt-1.5">
                <div className="font-display text-[20px] font-extrabold uppercase tracking-tight">
                  {step.title}
                </div>
                <p className="mt-1.5 max-w-[58ch] text-[14.5px] leading-relaxed text-ash">
                  {step.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
