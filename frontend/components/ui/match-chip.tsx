import { cn } from "@/lib/utils";

/**
 * MatchChip — the green "interested buyers" pill (trust colour, never amber).
 * Feeds from G1 match_count_within_5km.
 */
export function MatchChip({
  count,
  className,
}: {
  count: number;
  className?: string;
}) {
  return (
    <span
      data-testid="match-chip"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill bg-[#E7F4EC] px-3 py-1.5 font-sans text-[11px] font-bold text-trust",
        className,
      )}
    >
      <span className="text-[8px] leading-none">●</span>
      <span className="tnum">{count}</span>
      interested {count === 1 ? "buyer" : "buyers"} within 5 km
    </span>
  );
}
