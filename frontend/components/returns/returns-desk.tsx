"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PhoneFrame } from "@/components/ui/phone-frame";
import { DarkStage } from "@/components/ui/dark-stage";
import { Button } from "@/components/ui/button";
import { StatChip } from "@/components/ui/stat-chip";
import { itemsService } from "@/lib/services";
import { uploadPhotos } from "@/lib/upload";
import { DEMO_ITEM, DEMO_ITEM_ID, journey } from "@/lib/demo";
import { Camera, Plus, RotateCcw, AlertTriangle } from "lucide-react";

type Phase = "capture" | "error";

interface Shot {
  file: File;
  url: string;
}

/**
 * Phase 2 / spine step 1 — Returns Desk. Order context chips + photo capture
 * (2–4) + batch strip. On Grade it starts the ONE demo journey (deterministic
 * `itm_demo` id), kicks off the real async grade, and hands off to the folded
 * inspection beat (`/scanner?item=...`) which advances to the reveal on
 * grade-land. Transport errors show a retry.
 */
export function ReturnsDesk() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("capture");
  const [shots, setShots] = useState<Shot[]>([]);
  const [simBlurry, setSimBlurry] = useState(false);
  const [errMsg, setErrMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    journey.setBeat("capture");
  }, []);

  const addShots = (files: FileList | null) => {
    if (!files) return;
    const next = Array.from(files)
      .slice(0, 4 - shots.length)
      .map((file) => ({ file, url: URL.createObjectURL(file) }));
    setShots((s) => [...s, ...next].slice(0, 4));
  };

  const grade = useCallback(async () => {
    try {
      setErrMsg("");
      const meta = await itemsService.createItem({
        context_source: "order_scan",
        category: DEMO_ITEM.category,
        age_months: DEMO_ITEM.age_months,
        order_id: DEMO_ITEM.order_id,
        item_id: DEMO_ITEM_ID, // deterministic spine id (mock honours)
      });
      const presign = await itemsService.presignPhotos(meta.item_id, shots.length);
      const keys = await uploadPhotos(
        meta.item_id,
        presign,
        shots.map((s) => s.file),
        itemsService.mode === "live",
      );
      // G5: stash the local preview for the reveal to render against.
      if (shots[0]) sessionStorage.setItem(`rb:photo:${meta.item_id}`, shots[0].url);
      const gradeKeys = simBlurry ? keys.map((k) => k + "?blurry") : keys;
      await itemsService.enqueueGrade(meta.item_id, gradeKeys);
      journey.start(meta.item_id);
      // Fold the 3D scan into the grade moment (default): inspect → verdict.
      router.push(`/scanner?item=${meta.item_id}`);
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "Grading could not start");
      setPhase("error");
    }
  }, [shots, simBlurry, router]);

  if (phase === "error") {
    return (
      <PhoneFrame where="Returns · Hub BLR-4">
        <div
          data-testid="error-state"
          className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center"
        >
          <div className="grid h-16 w-16 place-items-center rounded-full bg-[#FCE9E9]">
            <AlertTriangle className="h-7 w-7 text-sale" />
          </div>
          <div className="font-display text-[20px] font-extrabold uppercase tracking-tight">
            Couldn&apos;t start grading
          </div>
          <p className="tnum text-[12px] leading-relaxed text-ash">{errMsg}</p>
          <Button variant="primary" size="md" onClick={() => setPhase("capture")}>
            <RotateCcw className="h-4 w-4" /> Try again
          </Button>
        </div>
      </PhoneFrame>
    );
  }

  return (
    <PhoneFrame where="Returns · Hub BLR-4">
      <div className="flex flex-1 flex-col px-4 pb-5">
        <div className="mb-2 flex flex-wrap gap-2">
          <StatChip label="Order" value={DEMO_ITEM.order_id} />
          <StatChip label="Category" value="Shoes" />
          <StatChip label="Age" value="8 mo" />
        </div>

        <DarkStage ghost="SCAN" className="relative mt-1 h-[230px]" rounded="rounded-[24px]">
          <div className="pointer-events-none absolute inset-[18px] rounded-[18px] border-2 border-dashed border-amber/60" />
          <button
            data-testid="add-photo"
            onClick={() => fileRef.current?.click()}
            className="relative z-10 flex flex-col items-center gap-2 rounded-2xl bg-white/95 px-5 py-4 font-sans text-[12px] font-semibold text-ink shadow-md transition-transform hover:-translate-y-0.5"
          >
            {shots.length === 0 ? (
              <Camera className="h-6 w-6 text-amber-deep" />
            ) : (
              <Plus className="h-6 w-6 text-amber-deep" />
            )}
            {shots.length === 0 ? "Add the first photo" : "Add another angle"}
          </button>
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-pill bg-white/90 px-3 py-1.5 font-sans text-[11px] font-semibold text-ink shadow-md">
            {shots.length < 2 ? (
              <>
                Capture <span className="tnum">{2 - shots.length}</span> more —
                front, side, label
              </>
            ) : (
              <span className="text-trust">Ready to grade</span>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            data-testid="file-input"
            onChange={(e) => addShots(e.target.files)}
          />
        </DarkStage>

        <div className="mt-3 flex gap-2" data-testid="batch-strip">
          {Array.from({ length: 4 }).map((_, i) => {
            const shot = shots[i];
            return (
              <div
                key={i}
                className="flex h-14 flex-1 items-center justify-center overflow-hidden rounded-input border border-hair bg-paper"
              >
                {shot ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={shot.url}
                    alt={`Shot ${i + 1}`}
                    className="h-full w-full object-cover"
                    data-testid="thumb"
                  />
                ) : (
                  <span className="tnum text-[11px] text-stone">{i + 1}</span>
                )}
              </div>
            );
          })}
        </div>

        {itemsService.mode === "mock" && (
          <label className="mt-3 flex items-center gap-2 text-[11px] text-mute">
            <input
              type="checkbox"
              data-testid="sim-blurry"
              checked={simBlurry}
              onChange={(e) => setSimBlurry(e.target.checked)}
            />
            Simulate a blurry capture (forces RETAKE_REQUIRED)
          </label>
        )}

        <Button
          variant={shots.length >= 2 ? "primary" : "idle"}
          size="block"
          disabled={shots.length < 2}
          data-testid="grade-btn"
          onClick={grade}
          className="mt-auto"
        >
          Grade{" "}
          {shots.length > 0 ? <span className="tnum ml-1">{shots.length}</span> : null}{" "}
          {shots.length === 1 ? "photo" : "photos"}
        </Button>
      </div>
    </PhoneFrame>
  );
}
