"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useRole, roleStore } from "@/lib/role";
import { Button } from "@/components/ui/button";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Receipt, type ReceiptRow } from "@/components/ui/receipt";
import { StatusLine } from "@/components/ui/status-line";
import { MatchChip } from "@/components/ui/match-chip";
import { ProductGlyph } from "@/components/product-glyph";
import { itemsService, matchingService } from "@/lib/services";
import { uploadPhotos } from "@/lib/upload";
import { useGradePoll } from "@/lib/hooks/use-grade-poll";
import { formatMoney, formatSignedMoney } from "@/lib/format";
import {
  AlertTriangle,
  ArrowRight,
  Camera,
  Package,
  Plus,
  RotateCcw,
  ShoppingBag,
  UserCog,
  X,
  MapPin,
  Check
} from "lucide-react";

type Category = "shoes" | "tech" | "baby" | "books" | "home";
type Stage = "capture" | "grading" | "verdict" | "retake" | "routed" | "error";

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

interface Shot {
  id: string;
  file: File;
  url: string;
}

export default function ReturnHandlePage() {
  const role = useRole();
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("capture");
  const [shots, setShots] = useState<Shot[]>([]);
  const [simBlurry, setSimBlurry] = useState(false);
  const [errMsg, setErrMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<HTMLDivElement>(null);

  const [orderId, setOrderId] = useState("");
  const [category, setCategory] = useState<Category>("shoes");
  const [ageMonths, setAgeMonths] = useState(0);
  const [itemId, setItemId] = useState<string | null>(null);

  const addShots = (files: FileList | File[] | null) => {
    if (!files) return;
    const arr = Array.from(files)
      .filter((f) => f.type.startsWith("image/"))
      .slice(0, 4 - shots.length);
    const next = arr.map((file) => ({
      id: "s_" + Math.random().toString(36).slice(2),
      file,
      url: URL.createObjectURL(file),
    }));
    setShots((s) => [...s, ...next].slice(0, 4));
  };

  const removeShot = (id: string) =>
    setShots((s) => s.filter((x) => x.id !== id));

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragRef.current?.classList.remove("ring-amber");
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        f.type.startsWith("image/")
      );
      if (files.length) addShots(files);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [shots.length]
  );

  const startGrade = useCallback(async () => {
    try {
      setStage("grading");
      setErrMsg("");
      const meta = await itemsService.createItem({
        context_source: "order_scan",
        category,
        age_months: ageMonths,
        order_id: orderId || undefined,
      });
      const presign = await itemsService.presignPhotos(
        meta.item_id,
        shots.length
      );
      const keys = await uploadPhotos(
        meta.item_id,
        presign,
        shots.map((s) => s.file),
        itemsService.mode === "live"
      );
      const urls = shots.map((s) => s.url);
      if (urls.length > 0) {
        sessionStorage.setItem(`rb:photo:${meta.item_id}`, urls[0]);
      }
      const gradeKeys = simBlurry ? keys.map((k) => k + "?blurry") : keys;
      await itemsService.enqueueGrade(meta.item_id, gradeKeys);
      setItemId(meta.item_id);
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "Grading could not start");
      setStage("error");
    }
  }, [shots, simBlurry, category, ageMonths, orderId]);

  const poll = useGradePoll(itemId);
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

  const routeItem = async () => {
    if (!grade || !decision || !itemId) return;
    try {
      await itemsService.createListing({
        item_id: itemId,
        category,
        price: decision.price,
        geohash5: "tdr1v",
      });
    } catch (e) {
      console.error("Failed to create listing", e);
    }
    setStage("routed");
  };

  const resetCapture = () => {
    setStage("capture");
    setItemId(null);
    setShots([]);
    setOrderId("");
  };

  const remaining = 4 - shots.length;
  const canGrade = shots.length >= 2 && orderId.trim().length > 0;

  if (role === "customer") {
    return (
      <main className="bg-canvas px-4 py-16 sm:px-6">
        <div className="mx-auto max-w-[720px]">
          <div className="rounded-card border border-hair bg-paper p-8 shadow-sm sm:p-10">
            <div className="grid h-14 w-14 place-items-center rounded-full bg-[#FFF2DF]">
              <ShoppingBag className="h-6 w-6 text-amber-deep" />
            </div>
            <h1 className="mt-5 font-display text-[clamp(24px,3.5vw,32px)] font-extrabold uppercase leading-tight tracking-tight">
              Return handling is operator-only
            </h1>
            <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
              The Return Product flow is where ReBridge operators process
              incoming returns — photograph, grade, and route each item to its
              best next owner. This view is gated by role.
            </p>
            <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
              Switch to <b>Operator</b> in the nav (or tap the button below) to
              access the return handling console.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button
                variant="primary"
                size="md"
                data-testid="become-operator-return"
                onClick={() => roleStore.set("operator")}
              >
                <UserCog className="h-4 w-4" /> Switch to Operator view
              </Button>
              <Link href="/market">
                <Button variant="secondary" size="md">
                  Back to Second Chance
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (stage === "error") {
    return (
      <main className="bg-canvas px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-[1200px]">
          <PageHeader />
          <div className="mt-10 mx-auto flex max-w-[520px] flex-col items-center gap-4 rounded-card border border-hair bg-paper p-10 text-center shadow-sm">
            <div className="grid h-16 w-16 place-items-center rounded-full bg-[#FCE9E9]">
              <AlertTriangle className="h-7 w-7 text-sale" />
            </div>
            <div className="font-display text-[22px] font-extrabold uppercase tracking-tight">
              Couldn&apos;t start grading
            </div>
            <p className="tnum text-[13px] leading-relaxed text-ash">
              {errMsg}
            </p>
            <Button variant="primary" size="md" onClick={() => setStage("capture")}>
              <RotateCcw className="h-4 w-4" /> Try again
            </Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto max-w-[1200px]">
        <PageHeader />
        <div className="mt-8">
          {stage === "capture" && (
            <div className="grid gap-8 lg:grid-cols-[1.05fr_minmax(0,400px)]">
              <div className="flex flex-col gap-4">
                <div
                  ref={dragRef}
                  data-testid="upload-stage"
                  onDragOver={(e) => {
                    e.preventDefault();
                    dragRef.current?.classList.add("ring-amber");
                  }}
                  onDragLeave={() => dragRef.current?.classList.remove("ring-amber")}
                  onDrop={onDrop}
                  className="relative grid min-h-[320px] place-items-center overflow-hidden rounded-card border-2 border-dashed border-hair bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)] ring-0 ring-amber ring-offset-0 transition-shadow"
                >
                  <div className="relative z-10 flex flex-col items-center gap-4 text-center text-white">
                    <div className="grid h-16 w-16 place-items-center rounded-full bg-white/95 text-ink shadow-md">
                      <Camera className="h-7 w-7 text-amber-deep" />
                    </div>
                    <div>
                      <div className="font-display text-[22px] font-extrabold uppercase tracking-tight">
                        Photograph the return
                      </div>
                      <p className="mt-1.5 max-w-[36ch] text-[13px] leading-relaxed text-white/70">
                        Drag photos in, or click below. Front, side, and label. We
                        need <span className="tnum">2–4</span> shots.
                      </p>
                    </div>
                    <button
                      type="button"
                      data-testid="add-photo"
                      disabled={remaining <= 0}
                      onClick={() => fileRef.current?.click()}
                      className={`inline-flex items-center gap-2 rounded-pill px-5 py-2.5 font-sans text-[13px] font-bold transition-transform ${remaining > 0 ? "bg-white text-ink hover:-translate-y-0.5" : "cursor-not-allowed bg-white/40 text-white/60"}`}
                    >
                      {shots.length === 0 ? <Camera className="h-4 w-4 text-amber-deep" /> : <Plus className="h-4 w-4 text-amber-deep" />}
                      {shots.length === 0 ? "Add first photo" : remaining > 0 ? `Add another (${remaining} left)` : "Photo limit reached"}
                    </button>
                    <span className="tnum font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
                      jpg · png · drag &amp; drop
                    </span>
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
                </div>

                <div className="grid grid-cols-4 gap-2.5" data-testid="batch-strip">
                  {Array.from({ length: 4 }).map((_, i) => {
                    const s = shots[i];
                    return (
                      <div
                        key={i}
                        className={`group relative flex h-20 items-center justify-center overflow-hidden rounded-card border bg-paper ${s ? "border-hair" : "border-dashed border-hair text-[11px] text-stone"}`}
                      >
                        {s ? (
                          <>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={s.url} alt={`Shot ${i + 1}`} data-testid="thumb" className="h-full w-full object-contain" />
                            <button
                              type="button"
                              onClick={() => removeShot(s.id)}
                              className="absolute right-1 top-1 grid h-5 w-5 place-items-center rounded-full bg-ink/80 text-white opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </>
                        ) : (
                          <span className="tnum">{i + 1}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <aside className="flex flex-col gap-5">
                <div className="rounded-card border border-hair bg-pearl p-5 shadow-sm">
                  <div className="flex items-center gap-2">
                    <Package className="h-4 w-4 text-amber-deep" />
                    <span className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">Order context</span>
                  </div>
                  <p className="mt-2 text-[12px] text-mute">
                    Enter the return order details. Helps the AI grade accurately and route to the best buyer.
                  </p>

                  <div className="mt-4 flex flex-col gap-4">
                    <Field label="Order ID">
                      <input
                        data-testid="order-input"
                        value={orderId}
                        onChange={(e) => setOrderId(e.target.value)}
                        placeholder="e.g. AMZ-7F3A"
                        className="tnum w-full rounded-input border border-hair bg-white px-3 py-2.5 font-mono text-[13px] focus:border-ink focus:outline-none"
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
                          <option key={c.id} value={c.id}>{c.label}</option>
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
                        <span className="tnum w-16 text-right text-[13px] font-semibold">{ageMonths} mo</span>
                      </div>
                    </Field>
                  </div>
                </div>

                <div className="rounded-card border border-hair bg-paper p-5 shadow-sm">
                  <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">How it works</div>
                  <ul className="mt-3 space-y-2.5 text-[12.5px] text-ash">
                    <li className="flex items-start gap-2"><span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />Add 2–4 photos of the returned item</li>
                    <li className="flex items-start gap-2"><span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />AI grades condition, defects &amp; completeness</li>
                    <li className="flex items-start gap-2"><span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />Auto-routes to resale, refurb, or donation</li>
                    <li className="flex items-start gap-2"><span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-trust" />Health Card generated for the buyer</li>
                  </ul>
                </div>

                {itemsService.mode === "mock" && (
                  <label className="flex items-start gap-2 rounded-card border border-dashed border-hair bg-paper px-3 py-2.5 text-[11.5px] text-mute">
                    <input type="checkbox" data-testid="sim-blurry" checked={simBlurry} onChange={(e) => setSimBlurry(e.target.checked)} className="mt-0.5" />
                    <span><span className="font-semibold text-ink">Demo:</span> simulate a blurry capture so the AI requests a retake.</span>
                  </label>
                )}

                <div className="flex flex-col gap-2">
                  <Button variant={canGrade ? "primary" : "idle"} size="block" disabled={!canGrade} data-testid="grade-btn" onClick={startGrade}>
                    <Camera className="h-4 w-4" /> Grade return {shots.length > 0 ? <span className="tnum ml-1">({shots.length} photo{shots.length !== 1 ? "s" : ""})</span> : null}
                  </Button>
                  {!orderId.trim() && shots.length >= 2 && (
                    <p className="text-center text-[11px] text-sale">Enter an Order ID to proceed.</p>
                  )}
                </div>
              </aside>
            </div>
          )}

          {stage === "grading" && <GradingView previewUrl={previewUrl} category={category} />}

          {stage === "retake" && (
            <div data-testid="retake-state" className="mx-auto flex max-w-[520px] flex-col items-center gap-4 rounded-card border border-hair bg-paper p-10 text-center shadow-sm">
              <div className="grid h-16 w-16 place-items-center rounded-full bg-[#FCE9E9]">
                <AlertTriangle className="h-7 w-7 text-sale" />
              </div>
              <div className="font-display text-[22px] font-extrabold uppercase tracking-tight">Retake required</div>
              <p className="max-w-[44ch] text-[13.5px] leading-relaxed text-ash">One of the photos was too blurry to grade confidently.</p>
              <Button variant="primary" size="md" onClick={resetCapture} data-testid="retake-btn"><RotateCcw className="h-4 w-4" /> Retake photos</Button>
            </div>
          )}

          {stage === "verdict" && grade && (
            <div className="grid gap-8 lg:grid-cols-[1.05fr_minmax(0,420px)]">
              <div>
                <div className="relative grid aspect-[4/3] place-items-center overflow-hidden rounded-card border border-hair bg-paper">
                  {previewUrl ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img src={previewUrl} alt="Product preview" className="absolute inset-0 h-full w-full object-contain p-4" />
                  ) : (
                    <ProductGlyph kind={THUMB_BY_CATEGORY[category]} className="w-[55%]" />
                  )}
                  <div className="absolute left-4 top-4 flex items-center gap-2 rounded-pill bg-white/95 py-1.5 pl-2 pr-3.5 shadow-md">
                    <GradeBadge grade={grade.grade} size="sm" />
                    <span className="tnum text-[11px] font-semibold text-ash">{Math.round(grade.confidence * 100)}% confidence</span>
                  </div>
                </div>
                <div className="mt-5 grid gap-2 sm:grid-cols-2">
                  {grade.defects.map((d, i) => (
                    <div key={i} className="flex items-start gap-2 rounded-card border border-hair bg-paper p-3 text-[12.5px]">
                      <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />
                      <span><b className="font-semibold capitalize">{d.severity}</b> at {d.location}</span>
                    </div>
                  ))}
                </div>
              </div>

              <aside className="flex flex-col gap-4">
                <div className="rounded-card border border-hair bg-pearl p-5 shadow-md">
                  <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">Verdict</div>
                  <div className="mt-2 flex items-center gap-3">
                    <GradeBadge grade={grade.grade} size="md" />
                    <Price value={decision?.price ?? "0"} priceNew={decision?.price_new ?? undefined} size="lg" />
                  </div>
                  <div className="mt-3"><ConfidenceMeter value={grade.confidence} countUp={false} /></div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-[11.5px] text-mute">
                    <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> BLR-4</span>
                    <MatchChip count={matches.data?.match_count_within_5km ?? 0} />
                  </div>
                </div>
                {decision && (
                  <Receipt rows={[
                    { kind: "line", label: "Resale value · " + grade.grade, value: formatMoney(decision.value) },
                    { kind: "line", label: "AI grade + pickup", value: formatSignedMoney("-" + decision.cost), muted: true },
                    { kind: "rule" },
                    { kind: "total", label: "Margin", value: formatSignedMoney(decision.margin) },
                    { kind: "line", label: "vs liquidation", value: "−₹15", muted: true },
                    { kind: "route", label: "Route", value: `${decision.disposition} · ${matches.data?.match_count_within_5km ?? 0} buyers < 5 km` },
                  ]} />
                )}
                <Button variant="primary" size="block" onClick={routeItem} disabled={!decision}>
                  Route Item <ArrowRight className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" onClick={resetCapture}>← Start over</Button>
              </aside>
            </div>
          )}

          {stage === "routed" && (
            <div className="mx-auto flex max-w-[560px] flex-col items-center gap-5 rounded-card border border-hair bg-paper p-10 text-center shadow-sm">
              <div className="grid h-20 w-20 place-items-center rounded-full bg-[#E7F4EC]">
                <Check className="h-9 w-9 text-trust" strokeWidth={3} />
              </div>
              <div className="font-display text-[24px] font-extrabold uppercase tracking-tight">Item routed successfully</div>
              <p className="max-w-[42ch] text-[13.5px] leading-relaxed text-ash">
                The return for Order {orderId} has been graded and routed.
              </p>
              <Button variant="primary" size="md" onClick={resetCapture}>
                Process another return
              </Button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function PageHeader() {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">Operator · Return Product</div>
        <h1 className="mt-1 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">Handle a return</h1>
        <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
          Photograph the returned product, fill in the order context, and let the AI grade it. The item will be routed based on the grade.
        </p>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-sans text-[10px] font-bold uppercase tracking-[0.14em] text-stone">{label}</span>
      {children}
    </label>
  );
}

function GradingView({ previewUrl, category }: { previewUrl: string | null; category: Category }) {
  return (
    <div className="grid gap-8 lg:grid-cols-[1.05fr_minmax(0,420px)]">
      <div className="relative grid aspect-[4/3] place-items-center overflow-hidden rounded-card border border-hair bg-paper">
        {previewUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img src={previewUrl} alt="Inspecting" className="absolute inset-0 h-full w-full object-contain p-4" />
        ) : (
          <ProductGlyph kind={THUMB_BY_CATEGORY[category]} className="w-[55%]" />
        )}
        <div
          className="pointer-events-none absolute left-0 right-0 h-[60px] animate-[scanmove_1.4s_linear_infinite]"
          style={{
            background: "linear-gradient(180deg,transparent,rgba(255,153,0,.22),transparent)",
            borderTop: "2px solid rgba(255,153,0,.9)",
            boxShadow: "0 0 30px 6px rgba(255,153,0,.35)",
            top: "10%",
          }}
        />
      </div>
      <aside className="flex flex-col gap-4">
        <div className="rounded-card border border-hair bg-pearl p-5 shadow-sm">
          <div className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">Inspecting</div>
          <StatusLine text="Matching against original listing…" />
          <StatusLine text="Checking upper, soles, completeness…" />
          <StatusLine text="Computing route economics…" />
        </div>
        <p className="text-[12.5px] text-mute">
          We poll the worker every <span className="tnum">1.5s</span> and reveal the verdict the moment it lands.
        </p>
      </aside>
    </div>
  );
}
