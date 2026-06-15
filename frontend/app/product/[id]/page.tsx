"use client";

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { HealthCard } from "@/components/health-card";
import { Button } from "@/components/ui/button";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ProductGlyph } from "@/components/product-glyph";
import { healthCardService, matchingService } from "@/lib/services";
import { inventory } from "@/lib/inventory";
import { formatDistance, formatMoney } from "@/lib/format";
import { ArrowLeft, Check, MapPin, ShieldCheck, Truck } from "lucide-react";

export default function ProductDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [reserved, setReserved] = useState(false);
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [showToast, setShowToast] = useState(false);

  const card = useQuery({
    queryKey: ["health-card", id],
    queryFn: () => healthCardService.get(id),
    enabled: !!id,
  });

  const matches = useQuery({
    queryKey: ["matches", id],
    queryFn: () => matchingService.getMatches(id),
    enabled: !!id,
  });

  const top = matches.data?.matches[0];
  const distance = top?.distance_km ?? 4;

  // If the buyer has already reserved this item, reflect it.
  useEffect(() => {
    if (!id) return;
    const already = inventory.get().purchases.find((p) => p.item_id === id);
    if (already) setReserved(true);
  }, [id]);

  const onReserve = () => {
    if (!card.data) return;
    inventory.addPurchase({
      item_id: card.data.item_id,
      title: card.data.title,
      grade: card.data.grade,
      price: card.data.price,
      thumb_key: card.data.thumb_key,
      health_card_id: card.data.card_id,
      status: "RESERVED",
      reserved_at: new Date().toISOString(),
      pickup_at: "Tomorrow · 10:00–12:00",
    });

    setReserved(true);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 3000);
  };

  const pickupSlot = useMemo(() => "Tomorrow · 10:00–12:00", []);

  if (card.isLoading) {
    return (
      <main className="px-4 py-12 sm:px-6">
        <div className="mx-auto max-w-[1080px] text-[14px] text-mute">
          Loading…
        </div>
      </main>
    );
  }

  if (card.isError || !card.data) {
    return (
      <main className="px-4 py-12 sm:px-6">
        <div className="mx-auto max-w-[1080px]">
          <Link href="/market" className="inline-flex items-center gap-1.5 text-[13px] text-mute hover:text-ink">
            <ArrowLeft className="h-4 w-4" /> Back to Second Chance
          </Link>
          <div className="mt-6 rounded-card border border-hair bg-paper px-6 py-12 text-center text-[13px] text-sale">
            Couldn&apos;t load this Health Card.
          </div>
        </div>
      </main>
    );
  }

  const c = card.data;

  return (
    <main className="bg-canvas px-4 py-8 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-[1200px]">
        <Link
          href="/market"
          className="inline-flex items-center gap-1.5 font-sans text-[13px] font-semibold text-mute hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Second Chance
        </Link>

        <div className="mt-6 grid gap-8 lg:grid-cols-[1.1fr_minmax(0,420px)]">
          {/* Left: product gallery + summary */}
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-3">
              <div className="grid aspect-[16/11] w-full place-items-center overflow-hidden rounded-card border border-white/10 bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)]">
                <ProductGlyph
                  kind={c.images?.[activeImageIndex] || c.thumb_key}
                  fallbackCategory={c.title}
                  className="w-[55%] drop-shadow-[0_30px_36px_rgba(0,0,0,0.55)]"
                />
              </div>
              
              {c.images && c.images.length > 1 && (
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {c.images.map((img, idx) => (
                    <button
                      key={idx}
                      onClick={() => setActiveImageIndex(idx)}
                      className={`grid h-20 w-24 flex-shrink-0 place-items-center overflow-hidden rounded-[8px] border bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)] transition-all ${
                        activeImageIndex === idx ? "border-trust ring-2 ring-trust/20" : "border-white/10 opacity-60 hover:opacity-100"
                      }`}
                    >
                      <ProductGlyph kind={img} fallbackCategory={c.title} className="w-[60%]" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center gap-2 text-[12px] text-mute">
                <span className="inline-flex items-center gap-1 font-semibold text-trust">
                  <ShieldCheck className="h-3.5 w-3.5" /> ReBridge-verified
                </span>
                <span>·</span>
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" /> {formatDistance(distance)} from you
                </span>
              </div>
              <h1 className="mt-2 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">
                {c.title}
              </h1>
              <div className="mt-3 flex items-center gap-3">
                <GradeBadge grade={c.grade} size="md" />
                <Price value={c.price} priceNew={c.price_new} size="lg" />
              </div>
              <p className="mt-4 max-w-[58ch] text-[14.5px] leading-relaxed text-ash">
                AI-graded for ₹3, then human-spot-checked. Every finding listed
                below is on the verifiable Health Card — scan the QR with any
                phone to confirm the signature.
              </p>
              {top && (
                <div className="mt-4 inline-flex items-center gap-2 rounded-pill bg-[#E7F4EC] px-3 py-1.5 text-[12px] font-bold text-trust">
                  <span className="text-[8px] leading-none">●</span>
                  Why this is matched to you: {top.match_reasons[0]}
                </div>
              )}
            </div>

            {!reserved && <HealthCard card={c} showActions={false} />}
          </div>

          {/* Right: sticky buy panel */}
          <aside className="lg:sticky lg:top-[88px] lg:self-start">
            <div
              data-testid="buy-panel"
              className="flex flex-col gap-4 rounded-card border border-hair bg-pearl p-5 shadow-md"
            >
              <div className="flex items-center justify-between">
                <Price value={c.price} priceNew={c.price_new} size="lg" />
                <GradeBadge grade={c.grade} size="sm" />
              </div>
              <div className="grid gap-2 text-[12.5px] text-ink">
                <div className="flex items-center gap-2">
                  <Truck className="h-3.5 w-3.5 text-mute" />
                  <span className="text-ash">Pickup</span>
                  <span className="ml-auto tnum font-semibold">{pickupSlot}</span>
                </div>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-3.5 w-3.5 text-trust" />
                  <span className="text-ash">A-to-z guarantee</span>
                  <span className="ml-auto font-semibold text-trust">included</span>
                </div>
                <div className="mt-1 flex items-center gap-2 rounded bg-emerald-50 px-2 py-1.5 ring-1 ring-inset ring-emerald-200">
                  <span className="text-[12px] font-bold text-emerald-600">
                    +12 Green Credits
                  </span>
                  <span className="ml-auto text-[11px] text-emerald-600/80">
                    on reservation
                  </span>
                </div>
              </div>

              {reserved ? (
                <div
                  data-testid="reserved-state"
                  className="flex flex-col gap-3 rounded-card bg-[#E7F4EC] p-5 text-left"
                >
                  <div className="font-sans text-[13px] font-bold text-trust">
                    <Check className="mb-0.5 mr-1.5 inline-block h-4 w-4" />
                    Reserved — {c.title} · {c.grade} · {formatMoney(c.price)}
                  </div>
                  <div className="mt-1">
                    <div className="font-sans text-[14px] font-bold text-trust">
                      🌱 +{10 + (id.charCodeAt(id.length - 1) % 7)} Green Credits earned
                    </div>
                    <div className="mt-0.5 text-[12.5px] text-trust/90">
                      = 4.1 kg CO₂ saved · 612 km of reverse shipping avoided
                    </div>
                  </div>
                  <div className="mt-2 border-t border-trust/20 pt-3 text-[12.5px] font-bold text-trust">
                    You now have {47 + 10 + (id.charCodeAt(id.length - 1) % 7)} credits · ₹{Math.floor((47 + 10 + (id.charCodeAt(id.length - 1) % 7)) / 2)} toward your next order
                  </div>
                  <Link href="/notifications" className="mt-2">
                    <Button variant="secondary" size="sm" className="w-full bg-white/50 hover:bg-white/80">
                      View notification
                    </Button>
                  </Link>
                </div>
              ) : (
                <Button
                  variant="primary"
                  size="block"
                  data-testid="reserve-btn"
                  onClick={onReserve}
                >
                  Reserve · pay on pickup
                </Button>
              )}
              <p className="text-[11px] text-mute">
                Simulated checkout (v1 demo) — no payment is charged.
              </p>
            </div>

            <div className="mt-4 rounded-card border border-hair bg-paper p-4 text-[12.5px] text-ash">
              <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
                Why ReBridge
              </div>
              <ul className="mt-2 grid gap-1.5">
                <li>· Every grade is signed and tamper-evident.</li>
                <li>· Low-confidence grades go to a human reviewer first.</li>
                <li>· No middle-mile — handoffs stay local.</li>
              </ul>
            </div>
          </aside>
        </div>
      </div>
      
      {showToast && (
        <div className="fixed bottom-4 right-4 z-50 flex animate-in slide-in-from-bottom-5 items-center gap-2 rounded-lg bg-emerald-500 px-4 py-3 text-sm font-semibold text-white shadow-lg fade-in duration-300">
          <Check className="h-4 w-4" />
          +12 Green Credits earned
        </div>
      )}
    </main>
  );
}
