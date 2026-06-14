import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { StatChip } from "@/components/ui/stat-chip";
import { cn } from "@/lib/utils";

/**
 * Notification — the routing moment, reused from the kit. Two variants:
 *  - seller: "routed to N buyers < 5 km" (the loop closed for the returner)
 *  - buyer:  "a graded match near you"
 * Deep editorial green surface (the design's notif), trust copy, mono numbers.
 */
export function Notification({
  variant,
  className,
}: {
  variant: "seller" | "buyer";
  className?: string;
}) {
  const seller = variant === "seller";
  return (
    <div
      data-testid="notification"
      data-variant={variant}
      className={cn(
        "flex flex-col items-center gap-4 rounded-card bg-[radial-gradient(120%_90%_at_50%_20%,#15301f,#0d2417)] px-7 py-9 text-center",
        className,
      )}
    >
      <div className="relative grid h-20 w-20 place-items-center rounded-full bg-white/[0.06] text-[34px]">
        <span className="absolute inset-[-8px] animate-ring rounded-full border-2 border-[#1EAA52]/40" />
        {seller ? "🌱" : "🎁"}
      </div>
      <h4 className="font-display text-[20px] font-extrabold uppercase leading-tight tracking-tight text-white">
        {seller ? (
          <>
            Your shoes found
            <br />a new owner
          </>
        ) : (
          <>
            A graded match
            <br />
            near you
          </>
        )}
      </h4>
      {seller ? (
        <p className="max-w-[26ch] text-[12.5px] leading-relaxed text-[#A9CBB5]">
          Graded, re-priced, and picked up by someone nearby — instead of a 600 km
          trip to a warehouse.
        </p>
      ) : (
        <p className="max-w-[26ch] text-[12.5px] leading-relaxed text-[#A9CBB5]">
          A verified, ReBridge-graded item just matched your wishlist — 4 km away.
        </p>
      )}

      {seller ? (
        <span
          data-testid="notif-detail"
          className="tnum rounded-pill bg-white/10 px-3.5 py-1.5 font-mono text-[11px] font-semibold text-white"
        >
          routed to 3 buyers &lt; 5 km · 0.9 kg CO₂e saved
        </span>
      ) : (
        <div
          data-testid="notif-detail"
          className="flex items-center gap-2 rounded-pill bg-white/10 px-3 py-1.5"
        >
          <GradeBadge grade="Good" size="sm" />
          <Price value="340.00" size="sm" />
          <span className="tnum font-mono text-[11px] text-white">· 4 km</span>
        </div>
      )}
    </div>
  );
}
