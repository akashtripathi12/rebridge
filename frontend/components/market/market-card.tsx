"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import { matchingService } from "@/lib/services";
import { formatDistance, formatPercent } from "@/lib/format";
import type { MarketplaceItem } from "@/lib/schemas";

/**
 * MarketCard — a buyer tile. Leads with the black grade badge, amber price, and
 * distance (no star ratings). The "intent match" signal (why this was routed to
 * you) + match confidence come from the matching engine (G1), fetched per card.
 */
export function MarketCard({ item }: { item: MarketplaceItem }) {
  const matches = useQuery({
    queryKey: ["matches", item.item_id],
    queryFn: () => matchingService.getMatches(item.item_id),
  });
  const top = matches.data?.matches[0];

  return (
    <Link
      href={`/card/${item.item_id}`}
      data-testid="market-card"
      data-item={item.item_id}
      className="group overflow-hidden rounded-[14px] border border-hair-soft bg-pearl shadow-sm transition-transform hover:-translate-y-0.5"
    >
      <div className="grid h-[88px] place-items-center bg-[radial-gradient(130%_120%_at_40%_10%,#26262a,#141416)]">
        <ProductGlyph
          kind={item.thumb_key}
          className="w-[58%] drop-shadow-[0_8px_10px_rgba(0,0,0,0.5)]"
        />
      </div>
      <div className="p-3">
        <div className="font-sans text-[12px] font-bold leading-tight">
          {item.title}
        </div>
        <div className="mt-1.5 flex items-center gap-2">
          <GradeBadge grade={item.grade} size="sm" />
          <Price value={item.price} size="md" />
        </div>
        <div className="tnum mt-1.5 flex items-center gap-1.5 whitespace-nowrap text-[10px] text-mute">
          <span data-testid="market-distance">
            &lt; {formatDistance(item.distance_km)}
          </span>
          <span>· verified</span>
          {top ? (
            <span data-testid="market-confidence" className="text-trust">
              · {formatPercent(top.match_score)} match
            </span>
          ) : null}
        </div>
        {top ? (
          <div
            data-testid="market-intent"
            className="mt-2 inline-flex items-center gap-1.5 rounded-pill bg-[#E7F4EC] px-2.5 py-1 text-[10px] font-bold text-trust"
          >
            <span className="text-[7px] leading-none">●</span>
            {top.match_reasons[0]}
          </div>
        ) : null}
      </div>
    </Link>
  );
}
