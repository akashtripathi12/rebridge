"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Receipt, type ReceiptRow } from "@/components/ui/receipt";
import { StatusLine } from "@/components/ui/status-line";
import { MatchChip } from "@/components/ui/match-chip";
import { ProductGlyph } from "@/components/product-glyph";
import { PhotoUploader, type CapturedShot } from "./photo-uploader";
import { useGradePoll } from "@/lib/hooks/use-grade-poll";
import { itemsService, matchingService } from "@/lib/services";
import { uploadPhotos } from "@/lib/upload";
import { inventory } from "@/lib/inventory";
import { notifs } from "@/lib/notifications";
import { formatMoney, formatSignedMoney } from "@/lib/format";
import { AlertTriangle, ArrowRight, Camera, Check, MapPin, RotateCcw } from "lucide-react";

type Category = "shoes" | "tech" | "baby" | "books" | "home";

const CATEGORIES: { id: Category; label: string }[] = [
  { id: "shoes", label: "Shoes" },
  { id: "tech", label: "Tech" },
  { id: "baby", label: "Baby & kids" },
  { id: "books", label: "Books" },
  { id: "home", label: "Home" },
];

const THUMB_BY_CATEGORY: Record<Category, string> = {
  shoes: "shoe",
  tech: "earbuds",
  baby: "monitor",
  books: "books",
  home: "monitor",
};

type Stage = "capture" | "grading" | "verdict" | "retake" | "listed";

/**
 * ResellFlow — the working seller experience. Real page (not phone-mock):
 * capture stage on the left with a contextual order/category/age form on the
 * right, then a grading stage (inline scanner + status), then a verdict stage
 * (price + grade + receipt + List CTA), then a listed confirmation.
 */
export function ResellFlow() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("capture");
  const [shots, setShots] = useState<CapturedShot[]>([]);

  const [category, setCategory] = useState<Category>("shoes");
  const [ageMonths, setAgeMonths] = useState(8);
  const contextSource = "order_scan" as const;
  const [title, setTitle] = useState("Running Shoes · UK 7");
  const [simBlurry, setSimBlurry] = useState(false);
  const [itemId, setItemId] = useState<string | null>(null);

  const addShots = (files: FileList | File[]) => {
    const arr = Array.from(files).slice(0, 4 - shots.length);
    const next = arr.map((file) => ({
      id: `s_${Math.random().toString(36).slice(2)}`,
      file,
      url: URL.createObjectURL(file),
    }));
    setShots((s) => [...s, ...next].slice(0, 4));
  };
  const removeShot = (id: string) => setShots((s) => s.filter((x) => x.id !== id));

  const canGrade = shots.length >= 2 && title.trim().length > 0;

  const startGrade = useCallback(async () => {
    try {
      setStage("grading");
      const meta = await itemsService.createItem({
        context_source: contextSource,
        category,
        age_months: ageMonths,
      });
      const presign = await itemsService.presignPhotos(meta.item_id, shots.length);
      const keys = await uploadPhotos(
        meta.item_id,
        presign,
        shots.map((s) => s.file),
        itemsService.mode === "live",
      );
      // Keep the first preview around — used for the verdict tile.
      if (shots[0]) sessionStorage.setItem(`rb:photo:${meta.item_id}`, shots[0].url);
      const gradeKeys = simBlurry ? keys.map((k) => k + "?blurry") : keys;
      await itemsService.enqueueGrade(meta.item_id, gradeKeys);
      setItemId(meta.item_id);
    } catch (e) {
      console.error(e);
      setStage("capture");
    }
  }, [shots, category, ageMonths, simBlurry]);

  const poll = useGradePoll(itemId);
  // React to the poll terminal state.
  useEffect(() => {
    if (!poll.terminal) return;
    if (poll.status === "GRADED") setStage("verdict");
    else if (poll.status === "RETAKE_REQUIRED") setStage("retake");
    else setStage("retake");
  }, [poll.terminal, poll.status]);

  const matches = useQuery({
    queryKey: ["matches", itemId],
    enabled: stage === "verdict" && !!itemId,
    queryFn: () => matchingService.getMatches(itemId as string),
  });

  const grade = poll.data?.grade ?? null;
  const decision = poll.data?.decision ?? null;
  const previewUrl = itemId ? sessionStorage.getItem(`rb:photo:${itemId}`) : null;

  const list = () => {
    if (!grade || !decision || !itemId) return;
    inventory.addListing({
      item_id: itemId,
      title,
      category,
      grade: grade.grade,
      confidence: grade.confidence,
      price: decision.price,
      price_new: decision.price_new ?? undefined,
      thumb_key: THUMB_BY_CATEGORY[category],
      health_card_id: poll.data?.card?.card_id ?? `card_${itemId.slice(0, 6)}`,
      status: "LISTED",
      listed_at: new Date().toISOString(),
    });
    const matchCount = matches.data?.match_count_within_5km ?? 0;
    
    // 1. Notify the seller that their item was routed
    notifs.notifySellerOfRouting({
      title,
      grade: grade.grade,
      price: formatMoney(decision.price),
      matchCount,
    });

    // 2. Notify nearby buyers that a matched item is available
    if (matchCount > 0) {
      const topMatch = matches.data?.matches[0];
      notifs.notifyBuyersOfNewListing({
        title,
        grade: grade.grade,
        price: formatMoney(decision.price),
        itemId,
        matchCount,
        topDistance: topMatch?.distance_km,
        topReason: topMatch?.match_reasons?.[0],
      });
    }
    setStage("listed");
  };

  const resetCapture = () => {
    setStage("capture");
    setItemId(null);
    setShots([]);
  };

  // ----- Stage views -----
  if (stage === "capture") {
    return (
      <div className="grid gap-8 lg:grid-cols-[1.05fr_minmax(0,400px)]">
        <PhotoUploader shots={shots} onAdd={addShots} onRemove={removeShot} />

        <aside className="flex flex-col gap-5">
          <div className="rounded-card border border-hair bg-pearl p-5 shadow-sm">
            <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
              Context · Order scan
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-mute">
              Helps the model and the routing decision.
            </p>
          </div>

          <Field label="Product title">
            <input
              data-testid="title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Running Shoes · UK 7"
              className="w-full rounded-input border border-hair bg-white px-3 py-2.5 font-sans text-[13.5px] focus:border-ink focus:outline-none"
            />
          </Field>


          <Field label="Category">
            <select
              data-testid="cat-select"
              value={category}
              onChange={(e) => setCategory(e.target.value as Category)}
              className="w-full rounded-input border border-hair bg-white px-3 py-2.5 font-sans text-[13.5px] focus:border-ink focus:outline-none"
            >
              {CATEGORIES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Approx. age">
            <div className="flex items-center gap-3">
              <input
                type="range"
                data-testid="age-range"
                min={0}
                max={36}
                value={ageMonths}
                onChange={(e) => setAgeMonths(Number(e.target.value))}
                className="flex-1 accent-ink"
              />
              <span className="tnum w-16 text-right text-[13px] font-semibold">
                {ageMonths} mo
              </span>
            </div>
          </Field>

          {itemsService.mode === "mock" && (
            <label className="flex items-start gap-2 rounded-card border border-dashed border-hair bg-paper px-3 py-2.5 text-[11.5px] text-mute">
              <input
                type="checkbox"
                data-testid="sim-blurry"
                checked={simBlurry}
                onChange={(e) => setSimBlurry(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                <span className="font-semibold text-ink">Demo:</span> simulate a
                blurry capture so the AI requests a retake.
              </span>
            </label>
          )}

          <div className="flex flex-col gap-2">
            <Button
              variant={canGrade ? "primary" : "idle"}
              size="block"
              disabled={!canGrade}
              data-testid="grade-btn"
              onClick={startGrade}
            >
              <Camera className="h-4 w-4" /> Grade my item (₹3)
            </Button>
            <p className="text-center text-[11px] text-mute">
              Takes ~5s. Your bytes go straight to S3 — never through us in plaintext.
            </p>
          </div>
        </aside>
      </div>
    );
  }

  if (stage === "grading") {
    return (
      <GradingView previewUrl={previewUrl} />
    );
  }

  if (stage === "retake") {
    return (
      <div
        data-testid="retake-state"
        className="mx-auto flex max-w-[520px] flex-col items-center gap-4 rounded-card border border-hair bg-paper p-10 text-center shadow-sm"
      >
        <div className="grid h-16 w-16 place-items-center rounded-full bg-[#FCE9E9]">
          <AlertTriangle className="h-7 w-7 text-sale" />
        </div>
        <div className="font-display text-[22px] font-extrabold uppercase tracking-tight">
          Retake required
        </div>
        <p className="max-w-[44ch] text-[13.5px] leading-relaxed text-ash">
          One of the photos was too blurry to grade confidently. We&apos;d rather
          ask for a retake than guess — that&apos;s how the Health Card stays
          honest.
        </p>
        <Button variant="primary" size="md" onClick={resetCapture} data-testid="retake-btn">
          <RotateCcw className="h-4 w-4" /> Retake photos
        </Button>
      </div>
    );
  }

  if (stage === "verdict" && grade) {
    const rows: ReceiptRow[] = decision
      ? [
        {
          kind: "line",
          label: `Resale value · ${grade.grade}`,
          value: formatMoney(decision.value),
        },
        {
          kind: "line",
          label: "AI grade ₹3 + pickup",
          value: formatSignedMoney(`-${decision.cost}`),
          muted: true,
        },
        { kind: "rule" },
        { kind: "total", label: "Margin", value: formatSignedMoney(decision.margin) },
        { kind: "line", label: "vs liquidation", value: "−₹15", muted: true },
        {
          kind: "route",
          label: "Route",
          value: `${decision.disposition} · ${matches.data?.match_count_within_5km ?? 0} buyers < 5 km`,
        },
      ]
      : [];
    return (
      <div className="grid gap-8 lg:grid-cols-[1.05fr_minmax(0,420px)]">
        <div>
          {/* Product preview */}
          <div className="relative grid aspect-[16/11] place-items-center overflow-hidden rounded-card border border-white/10 bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)]">
            {previewUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={previewUrl}
                alt={title}
                className="h-[78%] w-[78%] object-contain drop-shadow-[0_24px_30px_rgba(0,0,0,0.55)]"
              />
            ) : (
              <ProductGlyph
                kind={THUMB_BY_CATEGORY[category]}
                className="w-[55%] drop-shadow-[0_24px_30px_rgba(0,0,0,0.55)]"
              />
            )}
            <div
              data-testid="grade-stamp"
              className="absolute left-4 top-4 flex items-center gap-2 rounded-pill bg-white/95 py-1.5 pl-2 pr-3.5 shadow-md"
            >
              <GradeBadge grade={grade.grade} size="sm" />
              <span className="tnum text-[11px] font-semibold text-ash">
                {Math.round(grade.confidence * 100)}% confidence
              </span>
            </div>
          </div>

          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {grade.defects.map((d, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-card border border-hair bg-paper p-3 text-[12.5px]"
              >
                <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />
                <span>
                  <b className="font-semibold capitalize">{d.severity}</b> at{" "}
                  {d.location}
                </span>
              </div>
            ))}
            <div className="flex items-start gap-2 rounded-card border border-hair bg-paper p-3 text-[12.5px]">
              <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-trust" />
              <span>
                <b className="font-semibold">Matches the original listing</b>
              </span>
            </div>
          </div>
        </div>

        <aside className="flex flex-col gap-4">
          <div className="rounded-card border border-hair bg-pearl p-5 shadow-md">
            <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
              Verdict
            </div>
            <div className="mt-2 flex items-center gap-3">
              <GradeBadge grade={grade.grade} size="md" />
              <Price value={decision?.price ?? "0"} priceNew={decision?.price_new ?? undefined} size="lg" />
            </div>
            <div className="mt-3">
              <ConfidenceMeter value={grade.confidence} countUp={false} />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11.5px] text-mute">
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3 w-3" /> BLR-4
              </span>
              <MatchChip count={matches.data?.match_count_within_5km ?? 0} />
            </div>
          </div>

          <Receipt rows={rows} />

          <Button
            variant="primary"
            size="block"
            data-testid="list-cta"
            onClick={list}
            disabled={!decision}
          >
            List for {formatMoney(decision?.price)} <ArrowRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={resetCapture}>
            ← Start over
          </Button>
        </aside>
      </div>
    );
  }

  // listed
  if (stage === "listed") {
    return (
      <div
        data-testid="listed-state"
        className="mx-auto flex max-w-[560px] flex-col items-center gap-5 rounded-card border border-hair bg-paper p-10 text-center shadow-sm"
      >
        <div className="grid h-20 w-20 place-items-center rounded-full bg-[#E7F4EC]">
          <Check className="h-9 w-9 text-trust" strokeWidth={3} />
        </div>
        <div className="font-display text-[24px] font-extrabold uppercase tracking-tight">
          Listed · routing in progress
        </div>
        <p className="max-w-[42ch] text-[13.5px] leading-relaxed text-ash">
          {title} is live on Second Chance. We&apos;ve notified the{" "}
          <span className="tnum font-semibold text-ink">
            {matches.data?.match_count_within_5km ?? 3}
          </span>{" "}
          nearest buyers who&apos;ve shown intent in this category.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link href="/resell/listings">
            <Button variant="primary" size="md">
              View my listings →
            </Button>
          </Link>
          <Link href="/market">
            <Button variant="secondary" size="md">
              Browse Second Chance
            </Button>
          </Link>
        </div>
        <button
          onClick={resetCapture}
          className="text-[12px] font-semibold text-mute hover:text-ink"
        >
          + Resell another item
        </button>
      </div>
    );
  }

  return null;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-sans text-[10px] font-bold uppercase tracking-[0.14em] text-stone">
        {label}
      </span>
      {children}
    </label>
  );
}

function GradingView({ previewUrl }: { previewUrl: string | null }) {
  return (
    <div className="grid gap-8 lg:grid-cols-[1.05fr_minmax(0,420px)]">
      <div className="relative grid aspect-[16/11] place-items-center overflow-hidden rounded-card border border-white/10 bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)]">
        {previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt="Inspecting"
            className="h-[78%] w-[78%] object-contain drop-shadow-[0_24px_30px_rgba(0,0,0,0.55)]"
          />
        ) : (
          <ProductGlyph kind="shoe" className="w-[55%]" />
        )}
        <div
          data-testid="scan-line"
          className="pointer-events-none absolute left-0 right-0 h-[60px] animate-[scanmove_1.4s_linear_infinite]"
          style={{
            background:
              "linear-gradient(180deg,transparent,rgba(255,153,0,.22),transparent)",
            borderTop: "2px solid rgba(255,153,0,.9)",
            boxShadow: "0 0 30px 6px rgba(255,153,0,.35)",
            top: "10%",
          }}
        />
      </div>
      <aside className="flex flex-col gap-4">
        <div className="rounded-card border border-hair bg-pearl p-5 shadow-sm">
          <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
            Inspecting
          </div>
          <StatusLine text="Matching against original listing…" />
          <StatusLine text="Checking upper, soles, completeness…" />
          <StatusLine text="Computing route economics…" />
        </div>
        <p className="text-[12.5px] text-mute">
          We poll the worker every <span className="tnum">1.5s</span> and reveal
          the verdict the moment it lands.
        </p>
      </aside>
    </div>
  );
}
