"use client";

import { BEATS, BEAT_LABELS, useJourney, type Beat } from "@/lib/demo";
import { cn } from "@/lib/utils";

/**
 * JourneyRail — the slim progress indicator for the golden path. Shows which of
 * the five beats (Capture → Grade → Route → Buyer → Reserved) the presenter is
 * on, so a judge always sees the arc and never feels lost. `current` overrides
 * the store (each spine screen declares its beat on mount, but can also pass it).
 */
export function JourneyRail({ current }: { current?: Beat }) {
  const j = useJourney();
  const active: Beat = current ?? j.beat;
  const activeIdx = BEATS.indexOf(active);

  return (
    <div
      data-testid="journey-rail"
      data-beat={active}
      className="mx-auto mb-6 flex max-w-[640px] items-center justify-between gap-2"
      aria-label="Demo progress"
    >
      {BEATS.map((beat, i) => {
        const done = i < activeIdx;
        const isActive = i === activeIdx;
        return (
          <div key={beat} className="flex flex-1 items-center gap-2 last:flex-none">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "grid h-5 w-5 flex-none place-items-center rounded-full font-mono text-[10px] font-semibold",
                  isActive
                    ? "bg-ink text-white"
                    : done
                      ? "bg-trust text-white"
                      : "bg-hair text-stone",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "font-sans text-[11px] font-semibold uppercase tracking-wide",
                  isActive ? "text-ink" : done ? "text-trust" : "text-stone",
                )}
              >
                {BEAT_LABELS[beat]}
              </span>
            </div>
            {i < BEATS.length - 1 ? (
              <span
                className={cn(
                  "h-[2px] flex-1 rounded-full",
                  done ? "bg-trust" : "bg-hair",
                )}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
