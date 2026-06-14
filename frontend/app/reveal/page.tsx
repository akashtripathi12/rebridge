"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PhoneFrame } from "@/components/ui/phone-frame";
import { Button } from "@/components/ui/button";
import { GradingReveal, type RevealResult } from "@/components/reveal/grading-reveal";
import { JourneyRail } from "@/components/journey/journey-rail";
import { useGradePoll } from "@/lib/hooks/use-grade-poll";
import { itemsService, matchingService } from "@/lib/services";
import { journey } from "@/lib/demo";

/**
 * Phase 3 — The Grading Reveal. Demo mode: create a (mock or live) item, enqueue
 * a grade, then POLL the real meta.status (G6). The scan theatre runs while
 * GRADING; the staged reveal fires when the grade lands. ?item=ID + an object
 * URL stored in sessionStorage (from the Returns Desk) render the user's photo.
 */
export default function RevealPage() {
  const router = useRouter();
  const [itemId, setItemId] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [runKey, setRunKey] = useState(0);

  // Kick off a grading run (demo) or attach to an existing item from Returns.
  useEffect(() => {
    let cancelled = false;
    journey.setBeat("grade");
    const url = new URL(window.location.href);
    const existing = url.searchParams.get("item");
    if (existing) {
      setItemId(existing);
      setImageUrl(sessionStorage.getItem(`rb:photo:${existing}`));
      return;
    }
    (async () => {
      const meta = await itemsService.createItem({
        context_source: "order_scan",
        category: "shoes",
        age_months: 8,
        order_id: "AMZ-7F3A",
      });
      if (cancelled) return;
      await itemsService.enqueueGrade(meta.item_id, [
        `items/${meta.item_id}/photo-1`,
        `items/${meta.item_id}/photo-2`,
      ]);
      if (!cancelled) setItemId(meta.item_id);
    })();
    return () => {
      cancelled = true;
    };
  }, [runKey]);

  const poll = useGradePoll(itemId);
  const graded = poll.terminal && poll.status === "GRADED" && poll.data?.grade;

  // Fetch matches only once graded (addendum: call /matches when GRADED).
  const matches = useQuery({
    queryKey: ["matches", itemId],
    enabled: !!graded && !!itemId,
    queryFn: () => matchingService.getMatches(itemId as string),
  });

  const result: RevealResult | null =
    graded && poll.data?.grade
      ? {
          grade: poll.data.grade,
          decision: poll.data.decision ?? null,
          matchCount: matches.data?.match_count_within_5km ?? 0,
          disposition: poll.data.decision?.disposition ?? "P2P",
        }
      : null;

  const replay = useCallback(() => {
    setItemId(null);
    setImageUrl(null);
    setRunKey((k) => k + 1);
  }, []);

  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · 03 · The grading reveal
        </div>
        <h1 className="mt-2 font-display text-[34px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          Model latency as theatre
        </h1>
        <div className="mt-4 flex items-center gap-3">
          <Button
            variant="primary"
            size="sm"
            onClick={replay}
            data-testid="replay"
          >
            ▶ Replay the grading reveal
          </Button>
          <span className="text-[12px] text-mute">
            polls real <span className="tnum">meta.status</span> · respects
            reduced-motion · {itemsService.mode} grade /{" "}
            {matchingService.mode} matches
          </span>
        </div>

        <div className="mt-8">
          <JourneyRail current="grade" />
          <div className="flex justify-center">
            <PhoneFrame where="Returns · Hub BLR-4">
              <GradingReveal
                key={runKey}
                result={result}
                imageUrl={imageUrl}
                onList={() => {
                  journey.markListed();
                  router.push("/notifications?flow=1");
                }}
              />
            </PhoneFrame>
          </div>
        </div>
      </div>
    </main>
  );
}
