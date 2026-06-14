"use client";

import { ResellFlow } from "@/components/resell/resell-flow";

export default function ResellPage() {
  return (
    <main className="bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto max-w-[1200px]">
        <div>
          <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
            Resell
          </div>
          <h1 className="mt-1 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">
            Give it a next owner
          </h1>
        </div>
        <p className="mt-3 max-w-[60ch] text-[14.5px] leading-relaxed text-ash">
          Photograph the item, confirm the order/context, and we&apos;ll grade it
          and route it to the best next owner in seconds.
        </p>

        <div className="mt-10">
          <ResellFlow />
        </div>
      </div>
    </main>
  );
}
