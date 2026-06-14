"use client";

import { Sparkles, Tag, MapPin, Star } from "lucide-react";

/**
 * RecommendationBadge — a small pill badge showing WHY this item was
 * recommended. Uses the recommendation reason from the scoring engine.
 * Color varies by reason type for visual variety.
 */
export function RecommendationBadge({
  reason,
  variant = "default",
}: {
  reason: string;
  variant?: "default" | "deal" | "nearby" | "quality";
}) {
  const styles = {
    default: "bg-gradient-to-r from-trust/90 to-trust-bright/90 text-white",
    deal: "bg-gradient-to-r from-amber-deep/90 to-amber/90 text-white",
    nearby: "bg-gradient-to-r from-ink/85 to-charcoal/85 text-white",
    quality: "bg-gradient-to-r from-trust/90 to-trust-bright/90 text-white",
  };

  const Icon = variant === "deal" ? Tag : variant === "nearby" ? MapPin : variant === "quality" ? Star : Sparkles;

  return (
    <span
      data-testid="recommendation-badge"
      className={`inline-flex items-center gap-1 rounded-pill px-2.5 py-1 font-sans text-[10px] font-bold leading-none shadow-sm backdrop-blur-sm ${styles[variant]}`}
    >
      <Icon className="h-2.5 w-2.5 flex-none" />
      <span className="truncate max-w-[140px]">{reason}</span>
    </span>
  );
}

/** Pick the right badge variant from the recommendation reason text. */
export function badgeVariantFromReason(
  reason: string,
): "default" | "deal" | "nearby" | "quality" {
  if (reason.includes("off retail")) return "deal";
  if (reason.includes("km away")) return "nearby";
  if (reason.includes("Like New") || reason.includes("condition")) return "quality";
  return "default";
}
