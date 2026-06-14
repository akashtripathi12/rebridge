"use client";

import Link from "next/link";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { Button } from "@/components/ui/button";
import { ProductGlyph } from "@/components/product-glyph";
import { useInventory } from "@/lib/inventory";
import { cn } from "@/lib/utils";
import { Plus } from "lucide-react";

const STATUS_TONES: Record<string, string> = {
  LISTED: "bg-paper text-ash border-hair",
  RESERVED: "bg-[#FFF2DF] text-amber-deep border-transparent",
  SOLD: "bg-[#E7F4EC] text-trust border-transparent",
};

export default function MyListingsPage() {
  const { listings, purchases } = useInventory();

  return (
    <main className="bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto max-w-[1200px]">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
              My listings
            </div>
            <h1 className="mt-1 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">
              Things you&apos;ve given a next life
            </h1>
          </div>
          <Link href="/resell">
            <Button variant="primary" size="md" data-testid="new-listing">
              <Plus className="h-4 w-4" /> Resell another
            </Button>
          </Link>
        </div>

        <section className="mt-10">
          <h2 className="font-sans text-[11px] font-bold uppercase tracking-[0.16em] text-stone">
            Listed by you ({listings.length})
          </h2>
          {listings.length === 0 ? (
            <div
              data-testid="empty-listings"
              className="mt-3 grid place-items-center rounded-card border border-dashed border-hair bg-paper px-6 py-16 text-center"
            >
              <div className="font-display text-[20px] font-extrabold uppercase tracking-tight">
                Nothing listed yet
              </div>
              <p className="mt-2 max-w-[44ch] text-[13px] text-ash">
                Photograph a returned or unused item — we&apos;ll grade it and
                route it to its next owner.
              </p>
              <Link href="/resell" className="mt-5">
                <Button variant="primary" size="md">
                  Resell your first item
                </Button>
              </Link>
            </div>
          ) : (
            <div
              data-testid="listings-grid"
              className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
              {listings.map((l) => (
                <Link
                  key={l.item_id}
                  href={`/product/${l.item_id}`}
                  className="flex gap-4 rounded-card border border-hair bg-pearl p-4 shadow-sm transition-transform hover:-translate-y-0.5"
                >
                  <div className="grid h-20 w-20 flex-none place-items-center rounded-card bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)]">
                    <ProductGlyph kind={l.thumb_key} className="w-[70%]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-sans text-[13.5px] font-bold">
                      {l.title}
                    </div>
                    <div className="mt-1.5 flex items-center gap-2">
                      <GradeBadge grade={l.grade} size="sm" />
                      <Price value={l.price} priceNew={l.price_new} size="sm" />
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <span
                        className={cn(
                          "rounded-md border px-1.5 py-0.5 font-sans text-[10px] font-bold uppercase tracking-wider",
                          STATUS_TONES[l.status] ?? STATUS_TONES.LISTED,
                        )}
                      >
                        {l.status}
                      </span>
                      <span className="tnum text-[11px] text-mute">
                        {new Date(l.listed_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        {purchases.length > 0 && (
          <section className="mt-14">
            <h2 className="font-sans text-[11px] font-bold uppercase tracking-[0.16em] text-stone">
              You&apos;ve reserved ({purchases.length})
            </h2>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {purchases.map((p) => (
                <Link
                  key={p.item_id}
                  href={`/product/${p.item_id}`}
                  className="flex gap-4 rounded-card border border-hair bg-pearl p-4 shadow-sm transition-transform hover:-translate-y-0.5"
                >
                  <div className="grid h-20 w-20 flex-none place-items-center rounded-card bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)]">
                    <ProductGlyph kind={p.thumb_key} className="w-[70%]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-sans text-[13.5px] font-bold">
                      {p.title}
                    </div>
                    <div className="mt-1.5 flex items-center gap-2">
                      <GradeBadge grade={p.grade} size="sm" />
                      <Price value={p.price} size="sm" />
                    </div>
                    <div className="mt-2 text-[11px] text-mute">
                      Pickup · <span className="tnum">{p.pickup_at}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
