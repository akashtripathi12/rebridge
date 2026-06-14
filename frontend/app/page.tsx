import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { LiveDemo } from "@/components/landing/live-demo";
import { EconomicsDeep } from "@/components/landing/economics-deep";
import { TrustBand } from "@/components/landing/trust-band";

/**
 * The real product landing: hero → how it works → live ₹3 demo → unit economics →
 * trust. The hero CTAs go straight to the working app (Market / Resell) — there
 * is no "watch the guided demo" forced flow any more. The demo lives INSIDE the
 * landing as a scroll-into-view animation.
 */
export default function Home() {
  return (
    <main data-testid="landing">
      <Hero />
      <HowItWorks />
      <LiveDemo />
      <EconomicsDeep />
      <TrustBand />
    </main>
  );
}
