"use client";

import Link from "next/link";
import { ReviewConsole } from "@/components/review/review-console";
import { Button } from "@/components/ui/button";
import { useRole, roleStore } from "@/lib/role";
import { reviewService } from "@/lib/services";
import { ShieldCheck, UserCog } from "lucide-react";

export default function ReviewPage() {
  const role = useRole();

  if (role === "customer") {
    return (
      <main className="bg-canvas px-4 py-16 sm:px-6">
        <div className="mx-auto max-w-[720px]">
          <div className="rounded-card border border-hair bg-paper p-8 shadow-sm sm:p-10">
            <div className="grid h-14 w-14 place-items-center rounded-full bg-[#FFF2DF]">
              <ShieldCheck className="h-6 w-6 text-amber-deep" />
            </div>
            <h1 className="mt-5 font-display text-[clamp(24px,3.5vw,32px)] font-extrabold uppercase leading-tight tracking-tight">
              The operator-only side of ReBridge
            </h1>
            <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
              The Review Console is where ReBridge operators double-check the
              grades the AI is least sure about — sorted by value × uncertainty,
              with confirm/override/retake actions. Every override trains the
              model.
            </p>
            <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
              This view is gated by role. Switch to <b>Operator</b> in the nav (or
              tap the button below) to see the real console. In production this
              will come from auth.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button
                variant="primary"
                size="md"
                data-testid="become-operator"
                onClick={() => roleStore.set("operator")}
              >
                <UserCog className="h-4 w-4" /> Switch to Operator view
              </Button>
              <Link href="/market">
                <Button variant="secondary" size="md">
                  Back to Second Chance
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto max-w-[1200px]">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
              Operator · Review Console
            </div>
            <h1 className="mt-1 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">
              A human double-checks
            </h1>
            <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
              Low-confidence grades queue here, sorted by value × uncertainty.
              Confirm, override (which trains the model), or request a retake.{" "}
              <span className="tnum">{reviewService.mode}</span> backend.
            </p>
          </div>
        </div>

        <div className="mt-8">
          <ReviewConsole />
        </div>
      </div>
    </main>
  );
}
