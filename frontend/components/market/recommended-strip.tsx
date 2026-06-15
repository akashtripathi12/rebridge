"use client";

import { useRef } from "react";
import Link from "next/link";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import {
  RecommendationBadge,
  badgeVariantFromReason,
} from "./recommendation-badge";
import { formatDistance } from "@/lib/format";
import { ShieldCheck, ChevronLeft, ChevronRight } from "lucide-react";
import type { ScoredItem } from "@/lib/recommendations";

/**
 * RecommendedStrip — a horizontal scroll carousel for a recommendation section.
 * Shows a section title + icon, with smooth scroll-snap cards. Each card is a
 * compact product tile with the recommendation reason badge overlaid.
 */
export function RecommendedStrip({
  title,
  icon,
  items,
  testId,
}: {
  title: string;
  icon: React.ReactNode;
  items: ScoredItem[];
  testId?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  if (items.length === 0) return null;

  const scroll = (direction: "left" | "right") => {
    if (!scrollRef.current) return;
    const amount = scrollRef.current.clientWidth * 0.7;
    scrollRef.current.scrollBy({
      left: direction === "left" ? -amount : amount,
      behavior: "smooth",
    });
  };

  return (
    <section data-testid={testId} className="relative">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="font-display text-[18px] font-extrabold uppercase tracking-tight">
            {title}
          </h2>
          <span className="rounded-pill bg-ink/5 px-2 py-0.5 font-sans text-[10px] font-bold text-mute">
            {items.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => scroll("left")}
            aria-label="Scroll left"
            className="grid h-8 w-8 place-items-center rounded-full border border-hair bg-paper text-mute transition-colors hover:border-ink/30 hover:text-ink"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => scroll("right")}
            aria-label="Scroll right"
            className="grid h-8 w-8 place-items-center rounded-full border border-hair bg-paper text-mute transition-colors hover:border-ink/30 hover:text-ink"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Scroll container */}
      <div
        ref={scrollRef}
        className="scrollbar-none -mx-1 flex snap-x snap-mandatory gap-4 overflow-x-auto px-1 pb-2"
      >
        {items.map((item) => (
          <RecommendedCard key={item.item_id} item={item} />
        ))}
        {/* Peek spacer so last card isn't flush with edge */}
        <div className="w-1 flex-none" aria-hidden />
      </div>
    </section>
  );
}

/**
 * A compact product card used inside the recommended strip.
 * Shows the product with a recommendation reason badge overlay.
 */
function RecommendedCard({ item }: { item: ScoredItem }) {
  const variant = badgeVariantFromReason(item.recommendationReason);

  return (
    <Link
      href={`/product/${item.item_id}`}
      data-testid="recommended-card"
      data-item={item.item_id}
      className="group flex w-[220px] flex-none snap-start flex-col overflow-hidden rounded-card border border-hair bg-pearl shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
    >
      {/* Image + badge */}
      <div className="relative grid aspect-[4/3] place-items-center overflow-hidden bg-black">
        <ProductGlyph
          kind={item.thumb_key}
          fallbackCategory={item.category}
          className="w-[58%] transition-transform duration-300 group-hover:scale-105"
        />
        {/* Recommendation reason badge */}
        <div className="absolute bottom-2 left-2 right-2">
          <RecommendationBadge reason={item.recommendationReason} variant={variant} />
        </div>
        {/* Verified icon */}
        <span className="absolute left-2 top-2 inline-flex items-center justify-center rounded-pill bg-white/95 p-1.5 shadow-sm">
          <ShieldCheck className="h-3 w-3 text-trust" />
        </span>
        {/* Relevance score */}
        <span className="absolute right-2 top-2 rounded-pill bg-black/70 px-2 py-0.5 font-sans text-[10px] font-bold tabular-nums text-white backdrop-blur-sm">
          {Math.round(item.relevanceScore * 100)}% match
        </span>
      </div>

      {/* Info */}
      <div className="flex flex-col gap-1.5 p-3">
        <div className="truncate font-sans text-[13px] font-bold leading-tight text-ink">
          {item.title}
        </div>
        <div className="flex items-center justify-between gap-2">
          {item.grade && <GradeBadge grade={item.grade} size="sm" />}
          <Price value={item.price} priceNew={item.price_new} size="md" />
        </div>
        <div className="tnum flex items-center gap-1.5 text-[10px] text-mute">
          <span>&lt; {formatDistance(item.distance_km)}</span>
          {item.discountPct != null && item.discountPct > 0 && (
            <>
              <span>·</span>
              <span className="font-bold text-sale">{item.discountPct}% off</span>
            </>
          )}
        </div>
      </div>
    </Link>
  );
}
