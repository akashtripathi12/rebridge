"use client";

import { Suspense, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PhoneFrame } from "@/components/ui/phone-frame";
import { Notification } from "@/components/notification";
import { JourneyRail } from "@/components/journey/journey-rail";
import { Button } from "@/components/ui/button";
import { journey, DEMO_ITEM_ID } from "@/lib/demo";

function NotificationsContent() {
  const params = useSearchParams();
  const flow = params.get("flow") === "1";

  useEffect(() => {
    if (flow) journey.setBeat("route");
  }, [flow]);

  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · 06 · The loop closes
        </div>
        <h1 className="mt-2 font-display text-[34px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          The routing moment
        </h1>
        <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
          Both sides of the match, notified. The seller&apos;s return found a
          home; a buyer found a verified, nearby second-life item.
        </p>

        <div className="mt-8">
          {flow ? <JourneyRail current="route" /> : null}
          <div className="grid gap-8 sm:grid-cols-2">
            <div className="flex flex-col items-center gap-3">
              <PhoneFrame where="just now" brand>
                <div className="flex flex-1 items-center px-3 pb-4">
                  <Notification variant="seller" className="w-full" />
                </div>
              </PhoneFrame>
              <span className="font-sans text-[12px] font-semibold text-mute">
                Seller · Priya
              </span>
            </div>
            <div className="flex flex-col items-center gap-3">
              <PhoneFrame where="just now" brand>
                <div className="flex flex-1 items-center px-3 pb-4">
                  <Notification variant="buyer" className="w-full" />
                </div>
              </PhoneFrame>
              <span className="font-sans text-[12px] font-semibold text-mute">
                Buyer · Rahul
              </span>
            </div>
          </div>

          {flow ? (
            <div className="mt-8 flex justify-center">
              <Link href={`/market?from=${DEMO_ITEM_ID}`} data-testid="follow-to-buyer">
                <Button variant="primary" size="lg">
                  Follow it to the buyer →
                </Button>
              </Link>
            </div>
          ) : null}
        </div>
      </div>
    </main>
  );
}

export default function NotificationsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-canvas" />}>
      <NotificationsContent />
    </Suspense>
  );
}
