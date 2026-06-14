"use client";

import { useEffect, useState } from "react";
import { GradeBadge } from "@/components/ui/grade-badge";
import { Price } from "@/components/ui/price";
import { QrCode } from "@/components/ui/qr-code";
import { Button } from "@/components/ui/button";
import { ProductGlyph } from "@/components/product-glyph";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Check, ShieldCheck } from "lucide-react";
import type { HealthCardView } from "@/lib/schemas";

/** Classify a defect into a finding tone (bad / warn). */
function findingTone(severity: string): "bad" | "warn" {
  const s = severity.toLowerCase();
  return /crack|broken|tear|major|dead|missing/.test(s) ? "bad" : "warn";
}

/**
 * <HealthCard> — the verifiable Product Health Card (the trust primitive).
 * Boarding-pass artifact: dark product topband, perforated edge, verified tick,
 * grade + confidence, findings, a REAL QR to the verifiable URL + signature, and
 * price vs new. Renders the verified/unverified state the service returns.
 */
export function HealthCard({
  card,
  onReserve,
  showActions = true,
}: {
  card: HealthCardView;
  onReserve?: () => void;
  /** Hide the price/reserve footer when the page already exposes them. */
  showActions?: boolean;
}) {
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const qrValue = `${origin}/card/${card.item_id}`;

  return (
    <div
      data-testid="health-card"
      className="overflow-hidden rounded-[20px] border border-hair-soft bg-pearl shadow-md"
    >
      {/* dark product topband */}
      <div className="relative h-[150px] overflow-hidden bg-black">
        <ProductGlyph
          kind={card.thumb_key}
          className="absolute inset-0 h-full w-full object-contain"
        />
        <span className="absolute bottom-2.5 left-3.5 font-display text-[11px] font-extrabold uppercase tracking-[0.12em] text-white/50">
          ReBridge · Verified
        </span>
      </div>

      {/* perforated edge */}
      <div className="relative border-b-2 border-dashed border-hair">
        <span className="absolute -left-2.5 -top-[9px] h-[18px] w-[18px] rounded-full bg-canvas" />
        <span className="absolute -right-2.5 -top-[9px] h-[18px] w-[18px] rounded-full bg-canvas" />
      </div>

      {/* body */}
      <div className="px-[18px] pb-1 pt-3.5">
        <div className="flex items-center justify-between">
          <span className="font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
            Product Health Card
          </span>
          {card.verified ? (
            <span
              data-testid="verified-badge"
              className="flex items-center gap-1.5 font-sans text-[11px] font-bold text-trust"
            >
              <span className="grid h-4 w-4 place-items-center rounded-full bg-trust text-[9px] text-white">
                <Check className="h-2.5 w-2.5" strokeWidth={3} />
              </span>
              Verified
            </span>
          ) : (
            <span
              data-testid="unverified-badge"
              className="flex items-center gap-1.5 font-sans text-[11px] font-bold text-sale"
            >
              Tampered
            </span>
          )}
        </div>
        <h3 className="mb-0.5 mt-1.5 font-display text-[19px] font-extrabold uppercase tracking-tight">
          {card.title}
        </h3>
        <div className="tnum mb-2.5 text-[11.5px] text-mute">
          {card.signature} · graded by ReBridge AI
        </div>
      </div>

      {/* grade strip */}
      <div className="flex items-center gap-2.5 border-y border-hair-soft bg-paper px-[18px] py-2.5">
        <GradeBadge grade={card.grade} size="md" />
        <div className="flex-1">
          <ConfidenceMeter
            value={card.confidence}
            countUp={false}
            showBar={false}
            note="human-spot-checked"
          />
        </div>
      </div>

      {/* findings */}
      <div className="grid gap-2 px-[18px] py-3" data-testid="findings">
        {card.defects.map((d, i) => {
          const tone = findingTone(d.severity);
          return (
            <div key={i} className="flex gap-2.5 text-[12.5px] leading-snug">
              <i
                className={`mt-[5px] h-[7px] w-[7px] flex-none rounded-full ${
                  tone === "bad" ? "bg-sale" : "bg-amber-deep"
                }`}
              />
              <span>
                <b className="font-semibold capitalize">{d.severity}</b>, {d.location}{" "}
                — cosmetic only.
              </span>
            </div>
          );
        })}
        <div className="flex gap-2.5 text-[12.5px] leading-snug">
          <i className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-trust" />
          <span>
            <b className="font-semibold">Matches the original listing</b> — same
            item verified.
          </span>
        </div>
      </div>

      {/* footer: real QR + signature */}
      <div className="flex items-center gap-3 border-t border-dashed border-hair px-[18px] py-3">
        <QrCode value={qrValue} size={72} />
        <div className="text-[11px] leading-[1.55] text-mute">
          <b className="mb-0.5 flex items-center gap-1 font-mono text-[12px] text-ink">
            <ShieldCheck className="h-3.5 w-3.5 text-trust" /> Scan to verify
          </b>
          HMAC-signed, tamper-evident. Anyone can check — no account needed.
        </div>
      </div>

      {/* price + reserve */}
      {showActions ? (
      <div className="flex flex-col gap-3 px-[18px] pb-[18px]">
        <div className="flex items-end justify-between rounded-2xl border border-hair bg-pearl px-[18px] py-3.5">
          <Price value={card.price} priceNew={card.price_new} size="lg" />
        </div>
        <Button
          variant="primary"
          size="block"
          data-testid="reserve-btn"
          onClick={onReserve}
        >
          Reserve with ReBridge protection
        </Button>
        <div className="text-center font-sans text-[11px] text-mute">
          A-to-z guarantee · standard returns apply
        </div>
      </div>
      ) : null}
    </div>
  );
}
