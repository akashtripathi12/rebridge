"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { matchingService, marketplaceService } from "@/lib/services";
import { MARKETPLACE_ALL_CATEGORY } from "@/lib/market/constants";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import { Sparkles } from "lucide-react";

/**
 * MatchPushCard — the proactive routing moment for the persona: "a graded match
 * near you", with the top match reason from the engine (G1). Dark editorial card
 * (trust-green wash), one black CTA into the Health Card.
 */
export function MatchPushCard({ itemId }: { itemId: string }) {
  const matches = useQuery({
    queryKey: ["matches", itemId],
    queryFn: () => matchingService.getMatches(itemId),
  });
  const market = useQuery({
    queryKey: ["marketplace", MARKETPLACE_ALL_CATEGORY],
    queryFn: () => marketplaceService.list(MARKETPLACE_ALL_CATEGORY),
  });
  const item = market.data?.listings.find((l) => l.item_id === itemId);
  const reason = matches.data?.top_reason;

  if (!item) return null;

  return (
    <Link
      href={`/card/${itemId}`}
      data-testid="match-push"
      className="relative block overflow-hidden rounded-card border border-white/10 bg-[linear-gradient(110deg,#15301f,#0d2417)] p-4 text-white shadow-md"
    >
      <div className="flex items-center gap-2 font-sans text-[11px] font-bold uppercase tracking-[0.14em] text-[#1EAA52]">
        <Sparkles className="h-3.5 w-3.5" /> A graded match near you
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="grid h-14 w-14 flex-none place-items-center rounded-xl bg-white/5">
          <ProductGlyph kind={item.thumb_key} className="w-[78%]" />
        </div>
        <div className="min-w-0">
          <div className="truncate font-display text-[15px] font-extrabold uppercase tracking-tight">
            {item.title}
          </div>
          <div className="mt-1 flex items-center gap-2">
            <GradeBadge grade={item.grade} size="sm" />
            <Price value={item.price} size="sm" />
          </div>
          {reason ? (
            <div className="mt-1 text-[11px] text-[#A9CBB5]">
              Routed to you — {reason}
            </div>
          ) : null}
        </div>
      </div>
      <div className="mt-3 rounded-pill bg-white px-4 py-2.5 text-center font-sans text-[13px] font-bold text-ink">
        View Health Card
      </div>
    </Link>
  );
}
