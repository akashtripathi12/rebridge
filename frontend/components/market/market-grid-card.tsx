"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import { matchingService } from "@/lib/services";
import { formatDistance, formatPercent } from "@/lib/format";
import { ShieldCheck } from "lucide-react";
import {
  RecommendationBadge,
  badgeVariantFromReason,
} from "./recommendation-badge";
import type { MarketplaceItem } from "@/lib/schemas";

/**
 * MarketGridCard — the buyer tile for the real marketplace grid (NO phone
 * frame). Larger image, grade + amber price + distance + a match-confidence + a
 * single intent reason. Click → /product/[id] for buy.
 *
 * When `scoredReason` is provided (recommendation mode), overlays a
 * recommendation reason badge in the image area.
 */
export function MarketGridCard({
  item,
  scoredReason,
  scoredScore,
}: {
  item: MarketplaceItem;
  /** Recommendation reason from the scoring engine (optional). */
  scoredReason?: string;
  /** Relevance score 0–1 from the scoring engine (optional). */
  scoredScore?: number;
}) {
  const matches = useQuery({
    queryKey: ["matches", item.item_id],
    queryFn: () => matchingService.getMatches(item.item_id),
  });
  const top = matches.data?.matches[0];

  return (
    <Link
      href={`/product/${item.item_id}`}
      data-testid="market-card"
      data-item={item.item_id}
      className="group flex flex-col overflow-hidden rounded-card border border-hair bg-pearl shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="relative grid aspect-[4/3] place-items-center overflow-hidden bg-black">
        <ProductGlyph
          kind={item.thumb_key}
          fallbackCategory={item.category}
          className="w-[58%] transition-transform duration-300 group-hover:scale-105"
        />
        <span className="absolute left-3 top-3 inline-flex items-center justify-center rounded-pill bg-white/95 p-1.5 font-sans text-[10px] font-bold text-trust shadow-sm">
          <ShieldCheck className="h-3.5 w-3.5" />
        </span>
        {/* Recommendation badge overlay */}
        {scoredReason && (
          <div className="absolute bottom-2 left-2 right-2">
            <RecommendationBadge
              reason={scoredReason}
              variant={badgeVariantFromReason(scoredReason)}
            />
          </div>
        )}
        {/* Relevance score pill */}
        {scoredScore != null && (
          <span className="absolute right-2 top-2 rounded-pill bg-black/70 px-2 py-0.5 font-sans text-[10px] font-bold tabular-nums text-white backdrop-blur-sm">
            {Math.round(scoredScore * 100)}%
          </span>
        )}
      </div>
      <div className="flex flex-col gap-2 p-4">
        <div className="font-sans text-[14px] font-bold leading-tight text-ink">
          {item.title}
        </div>
        <div className="flex items-center justify-between gap-2">
          {item.grade && <GradeBadge grade={item.grade} size="sm" />}
          <Price value={item.price} priceNew={item.price_new} size="md" />
        </div>
        <div className="flex items-center gap-1.5 pt-0.5">
          <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 font-sans text-[10px] font-bold text-emerald-600 ring-1 ring-inset ring-emerald-200">
            +{10 + (item.item_id.charCodeAt(item.item_id.length - 1) % 7)} Green Credits
          </span>
        </div>
        <div className="tnum flex items-center gap-2 text-[11px] text-mute">
          <span data-testid="market-distance">
            &lt; {formatDistance(item.distance_km)}
          </span>
          {top ? (
            <>
              <span>·</span>
              <span data-testid="market-confidence" className="text-trust">
                {formatPercent(top.match_score)} match
              </span>
            </>
          ) : null}
        </div>
      </div>
    </Link>
  );
}

