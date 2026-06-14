"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import { matchingService } from "@/lib/services";
import { formatDistance, formatPercent } from "@/lib/format";
import { ShieldCheck } from "lucide-react";
import type { MarketplaceItem } from "@/lib/schemas";

/**
 * MarketGridCard — the buyer tile for the real marketplace grid (NO phone
 * frame). Larger image, grade + amber price + distance + a match-confidence + a
 * single intent reason. Click → /product/[id] for buy.
 */
export function MarketGridCard({ item }: { item: MarketplaceItem }) {
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
      <div className="relative grid aspect-[4/3] place-items-center overflow-hidden bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)]">
        <ProductGlyph
          kind={item.thumb_key}
          className="w-[58%] drop-shadow-[0_20px_24px_rgba(0,0,0,0.5)] transition-transform duration-300 group-hover:scale-105"
        />
        <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-pill bg-white/90 px-2 py-1 font-sans text-[10px] font-bold text-trust">
          <ShieldCheck className="h-3 w-3" /> Verified
        </span>
      </div>
      <div className="flex flex-col gap-2 p-4">
        <div className="font-sans text-[14px] font-bold leading-tight text-ink">
          {item.title}
        </div>
        <div className="flex items-center justify-between gap-2">
          <GradeBadge grade={item.grade} size="sm" />
          <Price value={item.price} priceNew={item.price_new} size="md" />
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
        {top ? (
          <div
            data-testid="market-intent"
            className="inline-flex w-fit items-center gap-1.5 rounded-pill bg-[#E7F4EC] px-2.5 py-1 text-[10.5px] font-bold text-trust"
          >
            <span className="text-[7px] leading-none">●</span>
            {top.match_reasons[0]}
          </div>
        ) : null}
      </div>
    </Link>
  );
}
