"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { formatPercent } from "@/lib/format";

/**
 * ConfidenceMeter — confidence is always visible (honest microcopy). Counts up
 * to the value (reduced-motion shows the final number immediately). Track is
 * trust-green; the number is mono.
 */
export function ConfidenceMeter({
  value,
  countUp = true,
  showBar = true,
  note,
  className,
}: {
  value: number; // 0..1
  countUp?: boolean;
  showBar?: boolean;
  note?: string;
  className?: string;
}) {
  const [shown, setShown] = useState(countUp ? 0 : value);
  const raf = useRef<number>();

  useEffect(() => {
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!countUp || reduced) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const dur = 900;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(value * eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [value, countUp]);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-center gap-2">
        <span
          data-testid="confidence-value"
          className="tnum text-[13px] font-semibold text-ink"
        >
          {formatPercent(shown)}
        </span>
        <span className="text-[12px] text-ash">confidence</span>
        {note ? <span className="text-[11px] text-mute">· {note}</span> : null}
      </div>
      {showBar ? (
        <div className="h-1.5 w-full overflow-hidden rounded-pill bg-hair">
          <div
            className="h-full rounded-pill bg-trust transition-[width] duration-300 ease-out"
            style={{ width: `${Math.round(shown * 100)}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}
