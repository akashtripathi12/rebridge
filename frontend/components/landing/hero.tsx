"use client";

import Link from "next/link";
import Image from "next/image";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import { prefersReducedMotion } from "@/lib/motion";
import { Magnetic } from "@/components/landing/magnetic";

/**
 * Hero — ReBridge's landing hero, rebuilt as an editorial composition where the
 * product object breaks through the headline.
 *
 * A towering Archivo headline ("Every product / finds its / next owner.") sits
 * as the back plane with amber reserved for the final word. An immersive R3F
 * product (a Higgsfield-generated, cut-out restored sneaker — see hero-scene.tsx)
 * floats IN FRONT of the type, overlapping the words exactly like a luxury
 * editorial cover. Behind everything: layered radial gradients, oversized ghost
 * typography (RE·USE / SECOND LIFE / CIRCULAR) with scroll parallax, a fine grain
 * veil and a soft vignette. Copy + two magnetic CTAs anchor the lower-left.
 *
 * Motion: a single GSAP entrance timeline staggers eyebrow → headline (masked
 * rise) → object → copy → CTAs with Apple-grade easing; a rAF-throttled scroll
 * handler drives parallax. Everything collapses to a composed static state under
 * prefers-reduced-motion, and the 3D scene mounts only when motion is allowed
 * (otherwise a static cutout shows in its place).
 */

const HeroScene = dynamic<{ onReady?: () => void }>(
  () => import("@/components/landing/hero-scene").then((m) => m.HeroScene),
  { ssr: false, loading: () => null },
);

const LINES = ["Every product", "finds its", "next owner."];

// Grain veil as inline SVG turbulence — no asset file, ~1KB, GPU-cheap.
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

export function Hero() {
  const rootRef = useRef<HTMLElement>(null);
  const headlineRef = useRef<HTMLHeadingElement>(null);
  const ghostRef = useRef<HTMLDivElement>(null);
  const objectRef = useRef<HTMLDivElement>(null);

  const [showScene, setShowScene] = useState(false);
  const [sceneReady, setSceneReady] = useState(false);

  useEffect(() => {
    const reduced = prefersReducedMotion();
    if (!reduced) setShowScene(true);

    const ctx = gsap.context(() => {
      const spans =
        headlineRef.current?.querySelectorAll("[data-line] > span") ?? [];

      if (reduced) {
        gsap.set(spans, { yPercent: 0, opacity: 1 });
        gsap.set("[data-reveal]", { opacity: 1, y: 0 });
        gsap.set(objectRef.current, { opacity: 1, y: 0 });
        return;
      }

      gsap.set(spans, { yPercent: 110, opacity: 0 });
      gsap.set("[data-reveal]", { opacity: 0, y: 22 });
      gsap.set(objectRef.current, { opacity: 0, y: 30 });

      const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
      tl.to("[data-eyebrow]", { opacity: 1, y: 0, duration: 0.6 }, 0.05)
        .to(spans, { yPercent: 0, opacity: 1, duration: 0.95, stagger: 0.1 }, 0.1)
        .to(objectRef.current, { opacity: 1, y: 0, duration: 1.1 }, 0.35)
        .to(
          "[data-reveal]:not([data-eyebrow])",
          { opacity: 1, y: 0, duration: 0.7, stagger: 0.08 },
          0.8,
        );
    }, rootRef);

    return () => ctx.revert();
  }, []);

  // Scroll parallax: ghost type drifts, headline lifts + fades, object shifts.
  useEffect(() => {
    if (prefersReducedMotion()) return;
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const y = window.scrollY;
        if (ghostRef.current)
          ghostRef.current.style.transform = `translate3d(0, ${y * 0.2}px, 0)`;
        if (objectRef.current)
          objectRef.current.style.setProperty("--py", `${y * -0.06}px`);
        if (headlineRef.current) {
          headlineRef.current.style.transform = `translate3d(0, ${y * -0.04}px, 0)`;
          headlineRef.current.style.opacity = String(Math.max(0, 1 - y / 900));
        }
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <section
      ref={rootRef}
      data-testid="hero"
      className="relative isolate flex min-h-[92vh] items-center overflow-hidden bg-canvas-warm px-4 pb-16 pt-16 sm:px-6 sm:pt-20"
    >
      {/* ── Background depth ───────────────────────────────────────────── */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(55% 50% at 72% 30%, rgba(255,153,0,0.12), transparent 62%)," +
            "radial-gradient(45% 40% at 14% 6%, rgba(255,255,255,0.7), transparent 70%)," +
            "radial-gradient(80% 65% at 50% 120%, rgba(17,17,17,0.07), transparent 60%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-50"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(17,17,17,0.04) 1px, transparent 1px)",
          backgroundSize: "min(33.333%, 400px) 100%",
          backgroundPosition: "center",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-[0.04] mix-blend-multiply"
        style={{ backgroundImage: GRAIN, backgroundSize: "180px 180px" }}
      />
      <div
        ref={ghostRef}
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 select-none will-change-transform"
      >
        <span className="absolute right-[-4%] top-[1%] font-display text-[clamp(120px,24vw,360px)] font-black uppercase leading-[0.8] tracking-[-0.05em] text-ink/[0.035]">
          RE·USE
        </span>
        <span className="absolute left-[-3%] top-[58%] font-display text-[clamp(64px,11vw,168px)] font-black uppercase leading-[0.8] tracking-[-0.04em] text-ink/[0.025]">
          Second life
        </span>
        <span className="absolute bottom-[4%] right-[7%] font-display text-[clamp(44px,7vw,108px)] font-black uppercase leading-[0.8] tracking-[-0.03em] text-amber/[0.06]">
          Circular
        </span>
      </div>

      {/* ── Composition ────────────────────────────────────────────────── */}
      <div className="relative mx-auto w-full max-w-[1240px]">
        {/* Headline + object share one stacking context: type is the back
            plane (z-10), the floating object breaks through in front (z-20). */}
        <div className="relative">
          <h1
            ref={headlineRef}
            data-testid="hero-headline"
            className="relative z-10 max-w-[15ch] font-display text-[clamp(52px,11.5vw,150px)] font-black uppercase leading-[0.88] tracking-[-0.045em] will-change-transform"
          >
            {LINES.map((line, i) => (
              <span key={i} data-line className="block overflow-hidden pb-[0.05em]">
                <span className="block">
                  {i === 2 ? (
                    <>
                      next{" "}
                      <span className="relative text-amber-deep">
                        owner.
                        <span
                          aria-hidden
                          className="absolute -bottom-1 left-0 h-[3px] w-full rounded-full bg-gradient-to-r from-amber to-amber-deep/0"
                        />
                      </span>
                    </>
                  ) : (
                    line
                  )}
                </span>
              </span>
            ))}
          </h1>

          {/* The floating product object — overlaps the headline from the right.
              Pointer events stay on (drag-to-inspect); it sits above the type
              but below the copy/CTAs which live outside this stack. */}
          <div
            ref={objectRef}
            data-testid="hero-image"
            className="absolute z-20 will-change-transform
                       right-[-8%] top-1/2 h-[clamp(300px,46vw,640px)] w-[clamp(300px,46vw,640px)] -translate-y-1/2
                       sm:right-[-4%]
                       lg:right-[-6%] lg:h-[640px] lg:w-[640px]"
            style={{ transform: "translateY(calc(-50% + var(--py, 0px)))" }}
          >
            {/* Static cutout — base layer for reduced-motion / no-WebGL and the
                seamless fallback while three streams in. */}
            <Image
              src="/hero/product.png"
              alt="A restored premium running sneaker floating — the ReBridge second-life object"
              fill
              priority
              sizes="(min-width: 1024px) 640px, 60vw"
              className="object-contain drop-shadow-[0_40px_60px_rgba(17,17,17,0.25)] transition-opacity duration-500"
              style={{ opacity: sceneReady ? 0 : 1 }}
            />
            {showScene && (
              <div className="absolute inset-0">
                <HeroScene onReady={() => setSceneReady(true)} />
              </div>
            )}
          </div>
        </div>

        {/* LOWER-LEFT — copy, CTAs, proof. Above the object stack so clickable. */}
        <div className="relative z-30 max-w-[52ch]">
          <p
            data-reveal
            className="mt-8 text-[16px] leading-relaxed text-ash sm:text-[17px]"
          >
            Photograph a returned, unused, or outgrown product. Our vision AI
            grades it in seconds, prints a verifiable Health Card, and a
            unit-economics router sends it onward —{" "}
            <span className="font-semibold text-ink">
              resale, refurb, peer-to-peer, or donation.
            </span>
          </p>

          <div data-reveal className="mt-9 flex flex-wrap items-center gap-3">
            <Magnetic strength={0.3}>
              <Link href="/market" data-testid="cta-market" className="group inline-block">
                <Button
                  variant="primary"
                  size="lg"
                  className="shadow-lg transition-shadow duration-300 hover:shadow-[0_24px_50px_-12px_rgba(17,17,17,0.45)]"
                >
                  Browse Second Chance
                </Button>
              </Link>
            </Magnetic>
            <Magnetic strength={0.25}>
              <Link href="/resell" data-testid="cta-resell" className="group inline-block">
                <Button variant="secondary" size="lg" className="hover:border-amber/40">
                  Resell an item
                  <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-pop group-hover:translate-x-1" />
                </Button>
              </Link>
            </Magnetic>
          </div>

          <a
            href="#how-it-works"
            data-reveal
            data-testid="scroll-cue"
            className="group mt-11 inline-flex items-center gap-2 font-sans text-[12px] font-bold uppercase tracking-[0.16em] text-mute transition-colors hover:text-ink"
          >
            See how it works
            <span className="inline-block transition-transform duration-300 group-hover:translate-y-1">
              ↓
            </span>
          </a>
        </div>
      </div>
    </section>
  );
}
