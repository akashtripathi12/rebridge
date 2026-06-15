"use client";

import { Suspense, useEffect } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { JourneyRail } from "@/components/journey/journey-rail";
import { StatusLine } from "@/components/ui/status-line";
import { Button } from "@/components/ui/button";
import { useGradePoll } from "@/lib/hooks/use-grade-poll";
import { journey } from "@/lib/demo";
import { seedGradedItem } from "@/lib/seed";
import { RotateCcw, AlertTriangle } from "lucide-react";

const ProductScanner = dynamic(
  () => import("@/components/scanner/product-scanner").then((m) => m.ProductScanner),
  {
    ssr: false,
    loading: () => (
      <div className="grid aspect-square w-full place-items-center rounded-card bg-[#0e0e10] font-mono text-[12px] text-white/50">
        Loading 3D studio…
      </div>
    ),
  },
);

/** Folded inspection beat: scan sweep + the real grade poll → advance to verdict. */
function InspectionMode({ itemId }: { itemId: string }) {
  const router = useRouter();
  const poll = useGradePoll(itemId);
  const grade = poll.data?.grade ?? seedGradedItem(itemId).grade!;

  useEffect(() => {
    journey.setBeat("grade");
  }, []);

  // On grade-land, advance to the verdict. Retake bounces back to capture.
  useEffect(() => {
    if (poll.terminal && poll.status === "GRADED") {
      const t = setTimeout(() => router.replace(`/reveal?item=${itemId}`), 700);
      return () => clearTimeout(t);
    }
  }, [poll.terminal, poll.status, itemId, router]);

  if (poll.terminal && poll.status === "RETAKE_REQUIRED") {
    return (
      <div
        data-testid="scanner-retake"
        className="mx-auto flex max-w-[460px] flex-col items-center gap-4 rounded-card border border-hair bg-paper p-8 text-center shadow-sm"
      >
        <div className="grid h-16 w-16 place-items-center rounded-full bg-[#FCE9E9]">
          <AlertTriangle className="h-7 w-7 text-sale" />
        </div>
        <div className="font-display text-[20px] font-extrabold uppercase tracking-tight">
          Retake required
        </div>
        <p className="text-[13px] leading-relaxed text-ash">
          A photo was too blurry to grade confidently — we&apos;d rather be sure
          than guess.
        </p>
        <Link href="/returns/handle">
          <Button variant="primary" size="md" data-testid="scanner-retake-btn">
            <RotateCcw className="h-4 w-4" /> Retake photos
          </Button>
        </Link>
      </div>
    );
  }


  const graded = poll.terminal && poll.status === "GRADED";

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,560px)_1fr]">
      <ProductScanner grade={grade} autoStart />
      <div className="flex flex-col justify-center gap-4">
        <StatusLine
          text={
            graded
              ? "Graded Good · taking you to the verdict…"
              : "Inspecting the upper & soles…"
          }
          done={graded}
        />
        <p className="max-w-[44ch] text-[13px] leading-relaxed text-ash">
          The ₹3 inspection, made visible — an amber sweep over the mesh while the
          grade resolves. The defects it surfaces are the ones on the Health Card.
        </p>
        {graded ? (
          <Link href={`/reveal?item=${itemId}`} data-testid="to-verdict">
            <Button variant="primary" size="md">
              See the verdict →
            </Button>
          </Link>
        ) : null}
      </div>
    </div>
  );
}

/** Cold standalone showcase (reached from the nav, not the spine). */
function StandaloneMode() {
  const grade = seedGradedItem("itm_shoe7").grade!;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,560px)_1fr]">
      <ProductScanner grade={grade} />
      <div className="flex flex-col justify-center gap-4">
        <div className="rounded-card border border-hair bg-paper p-5 shadow-sm">
          <div className="font-display text-[14px] font-bold uppercase tracking-tight text-ink">
            What you&apos;re seeing
          </div>
          <ul className="mt-3 space-y-2 text-[13px] leading-relaxed text-ash">
            <li>· Procedural sneaker placeholder (drops in a textured GLB later).</li>
            <li>· Amber scan sweep + Fresnel rim — the inspection made visible.</li>
            <li>· Defect hotspots pinned to the mesh (toe / sole / heel).</li>
            <li>· Idle auto-rotate; renders on demand, pauses when offscreen.</li>
          </ul>
        </div>
        <Link href="/returns/handle" className="font-sans text-[13px] font-semibold text-mute hover:text-ink">
          Run the full journey from the Returns Desk →
        </Link>
      </div>
    </div>
  );
}

function ScannerContent() {
  const params = useSearchParams();
  const item = params.get("item");
  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · 04 · {item ? "Inspecting" : "3D product scanner"}
        </div>
        <h1 className="mt-2 font-display text-[34px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          {item ? "The ₹3 inspection" : "Scan it on the stage"}
        </h1>
        <div className="mt-6">
          {item ? <JourneyRail current="grade" /> : null}
          {item ? <InspectionMode itemId={item} /> : <StandaloneMode />}
        </div>
      </div>
    </main>
  );
}

export default function ScannerPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-canvas" />}>
      <ScannerContent />
    </Suspense>
  );
}
