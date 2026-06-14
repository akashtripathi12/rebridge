"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { PhoneFrame } from "@/components/ui/phone-frame";
import { HealthCard } from "@/components/health-card";
import { JourneyRail } from "@/components/journey/journey-rail";
import { Button } from "@/components/ui/button";
import { healthCardService } from "@/lib/services";
import { journey } from "@/lib/demo";
import { ArrowLeft } from "lucide-react";

export default function CardPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [reserved, setReserved] = useState(false);

  useEffect(() => {
    journey.setBeat("buyer");
  }, []);

  const card = useQuery({
    queryKey: ["health-card", id],
    queryFn: () => healthCardService.get(id),
    enabled: !!id,
  });

  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <Link
          href="/market"
          className="inline-flex items-center gap-1.5 font-sans text-[13px] font-semibold text-mute hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Second Chance
        </Link>

        <div className="mt-6">
          <JourneyRail current={reserved ? "reserved" : "buyer"} />
          <div className="flex justify-center">
            <PhoneFrame where="Second Chance · 4 km">
              <div className="flex flex-1 flex-col gap-3 px-4 pb-5">
                {card.isLoading ? (
                  <div className="grid flex-1 place-items-center text-[13px] text-mute">
                    Loading Health Card…
                  </div>
                ) : card.isError || !card.data ? (
                  <div className="grid flex-1 place-items-center text-center text-[13px] text-sale">
                    Couldn&apos;t load this Health Card.
                  </div>
                ) : reserved ? (
                  <div
                    data-testid="confirmation"
                    className="flex flex-1 flex-col items-center justify-center gap-5 px-4 text-center"
                  >
                    <div className="relative grid h-24 w-24 place-items-center rounded-full bg-[#E7F4EC] text-[44px]">
                      <span className="absolute inset-[-8px] animate-ring rounded-full border-2 border-trust/40" />
                      🌱
                    </div>
                    <h2 className="font-display text-[24px] font-extrabold uppercase leading-tight tracking-tight">
                      A returned product just
                      <br />
                      started its second life
                    </h2>
                    <p className="max-w-[30ch] text-[13px] leading-relaxed text-ash">
                      {card.data.title} — reserved by a buyer 4 km away, graded
                      and verified by ReBridge. No warehouse round-trip.
                    </p>
                    <Link href="/" data-testid="back-to-hero">
                      <Button variant="primary" size="md">
                        Run it again →
                      </Button>
                    </Link>
                  </div>
                ) : (
                  <HealthCard
                    card={card.data}
                    onReserve={() => {
                      journey.markReserved();
                      setReserved(true);
                    }}
                  />
                )}
              </div>
            </PhoneFrame>
          </div>
        </div>
      </div>
    </main>
  );
}
