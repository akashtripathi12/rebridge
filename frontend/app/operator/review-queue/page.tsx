"use client";

import { ReviewConsole } from "@/components/review/review-console";
import { reviewService } from "@/lib/services";

/**
 * Operator landing — the Review Console. Low-confidence grades queue here,
 * sorted by value × uncertainty, with confirm / override / retake actions.
 * Access is enforced by the `/operator` group guard (and, authoritatively, by
 * the backend `RequireOperator` gate on the review endpoints).
 */
export default function ReviewQueuePage() {
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
