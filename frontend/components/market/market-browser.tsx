"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MarketGridCard } from "@/components/market/market-grid-card";
import { marketplaceService } from "@/lib/services";
import { MARKET_CATEGORIES } from "@/lib/market/constants";
import { useInventory } from "@/lib/inventory";
import { cn } from "@/lib/utils";
import { ShieldCheck, MapPin } from "lucide-react";

/**
 * Second-Chance marketplace browser — the customer-facing grid of verified
 * second-life products. Shared by the canonical customer landing
 * (`/marketplace`) and the legacy `/market` alias so there is one source of
 * truth for the browse experience.
 */
export function MarketBrowser() {
  const [category, setCategory] = useState(MARKET_CATEGORIES[0].id);
  const [sort, setSort] = useState<"distance" | "price-low" | "price-high">("distance");

  const market = useQuery({
    queryKey: ["marketplace", category],
    queryFn: () => marketplaceService.list(category),
  });

  const inv = useInventory();
  const myListedIds = useMemo(
    () => new Set(inv.listings.map((l) => l.item_id)),
    [inv.listings],
  );

  const listings = useMemo(() => {
    const base = (market.data?.listings ?? []).filter(
      (l) => !myListedIds.has(l.item_id),
    );
    const arr = [...base];
    if (sort === "distance") arr.sort((a, b) => a.distance_km - b.distance_km);
    if (sort === "price-low")
      arr.sort((a, b) => Number(a.price) - Number(b.price));
    if (sort === "price-high")
      arr.sort((a, b) => Number(b.price) - Number(a.price));
    return arr;
  }, [market.data, sort, myListedIds]);

  return (
    <main className="bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto max-w-[1200px]">
        {/* Page head */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
              Second Chance
            </div>
            <h1 className="mt-1 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">
              Verified second-life products near you
            </h1>
          </div>
          <div className="flex items-center gap-3 text-[12.5px] text-mute">
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5" /> Bengaluru · BLR-4
            </span>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-trust" /> A-to-z guarantee
            </span>
          </div>
        </div>

        {/* Filters */}
        <div
          data-testid="category-filter"
          className="mt-7 flex flex-wrap items-center gap-2 border-b border-hair pb-4"
        >
          {MARKET_CATEGORIES.map((c) => (
            <button
              key={c.id}
              data-testid={`cat-${c.id}`}
              onClick={() => setCategory(c.id)}
              className={cn(
                "rounded-pill border px-3 py-1.5 font-sans text-[12px] font-semibold transition-colors",
                category === c.id
                  ? "border-ink bg-ink text-white"
                  : "border-hair bg-paper text-ash hover:border-ink/30",
              )}
            >
              {c.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="sort" className="text-[11px] uppercase tracking-wider text-mute">
              Sort
            </label>
            <select
              id="sort"
              data-testid="sort-select"
              value={sort}
              onChange={(e) => setSort(e.target.value as typeof sort)}
              className="rounded-pill border border-hair bg-paper px-3 py-1.5 font-sans text-[12px] font-semibold"
            >
              <option value="distance">Nearest first</option>
              <option value="price-low">Price · low to high</option>
              <option value="price-high">Price · high to low</option>
            </select>
          </div>
        </div>

        {/* Grid */}
        {market.isLoading ? (
          <div className="mt-12 text-[13px] text-mute">Loading…</div>
        ) : listings.length === 0 ? (
          <div
            data-testid="market-empty"
            className="mt-16 grid place-items-center rounded-card border border-dashed border-hair bg-paper px-6 py-16 text-center"
          >
            <div className="font-display text-[20px] font-extrabold uppercase tracking-tight">
              Nothing nearby in this category yet
            </div>
            <p className="mt-2 max-w-[44ch] text-[13px] text-ash">
              Try another category — or be the first to{" "}
              <span className="font-semibold text-ink">Resell</span> something in
              this one.
            </p>
          </div>
        ) : (
          <div
            data-testid="market-grid"
            className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
          >
            {listings.map((item) => (
              <MarketGridCard key={item.item_id} item={item} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
