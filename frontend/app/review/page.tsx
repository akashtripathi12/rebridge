import { ReviewConsole } from "@/components/review/review-console";
import { reviewService } from "@/lib/services";

export default function ReviewPage() {
  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · 06 · Operator
        </div>
        <h1 className="mt-2 font-display text-[34px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          A human double-checks
        </h1>
        <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
          Low-confidence grades queue here, sorted by value × uncertainty.
          Confirm, override (which trains the model), or request a retake.{" "}
          <span className="tnum">{reviewService.mode}</span> backend.
        </p>

        <div className="mt-8">
          <ReviewConsole />
        </div>
      </div>
    </main>
  );
}
