"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PhoneFrame } from "@/components/ui/phone-frame";
import { MarketCard } from "@/components/market/market-card";
import { MatchPushCard } from "@/components/market/match-push-card";
import { JourneyRail } from "@/components/journey/journey-rail";
import { marketplaceService } from "@/lib/services";
import { MARKET_CATEGORIES } from "@/lib/market/constants";
import { RAHUL } from "@/lib/persona";
import { journey } from "@/lib/demo";
import { cn } from "@/lib/utils";

export default function MarketPage() {
  const [category, setCategory] = useState(MARKET_CATEGORIES[0].id);

  useEffect(() => {
    journey.setBeat("buyer");
  }, []);
  const market = useQuery({
    queryKey: ["marketplace", category],
    queryFn: () => marketplaceService.list(category),
  });
  const listings = market.data?.listings ?? [];

  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · 05 · Second Chance
        </div>
        <h1 className="mt-2 font-display text-[34px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          AI grades it. AI finds its buyer.
        </h1>
        <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
          Graded second-life items, routed to the right buyer by the matching
          engine. Every tile leads with grade + distance — never a star rating.
          Browsing as{" "}
          <span className="tnum font-semibold text-ink">
            {RAHUL.name} · {RAHUL.city} · intent: {RAHUL.intentCategory}
          </span>
          .
        </p>

        <div className="mt-8">
          <JourneyRail current="buyer" />
        </div>
        <div className="flex justify-center">
          <PhoneFrame where="Second Chance">
            <div className="flex flex-1 flex-col gap-3 px-3.5 pb-5">
              {/* Proactive routed match for the persona */}
              <MatchPushCard itemId={RAHUL.routedItemId} />

              {/* Category filter */}
              <div className="flex gap-1.5 overflow-x-auto" data-testid="category-filter">
                {MARKET_CATEGORIES.map((c) => (
                  <button
                    key={c.id}
                    data-testid={`cat-${c.id}`}
                    onClick={() => setCategory(c.id)}
                    className={cn(
                      "whitespace-nowrap rounded-pill border px-3 py-1.5 font-sans text-[10.5px] font-semibold transition-colors",
                      category === c.id
                        ? "border-ink bg-ink text-white"
                        : "border-hair bg-paper text-ash hover:border-ink/30",
                    )}
                  >
                    {c.label}
                  </button>
                ))}
              </div>

              {/* Grid */}
              {listings.length === 0 ? (
                <div
                  data-testid="market-empty"
                  className="grid flex-1 place-items-center text-center text-[13px] text-mute"
                >
                  Nothing in this category nearby yet.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2.5" data-testid="market-grid">
                  {listings.map((item) => (
                    <MarketCard key={item.item_id} item={item} />
                  ))}
                </div>
              )}
            </div>
          </PhoneFrame>
        </div>
      </div>
    </main>
  );
}
