"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { GradeBadge } from "@/components/ui/grade-badge";
import { QrCode } from "@/components/ui/qr-code";
import { ShieldCheck } from "lucide-react";

/**
 * TrustBand — the trust story under the demo. The Health Card explainer + a
 * pointer to the operator review console (so buyers know "a human double-checks
 * low scores"). Pitch chrome, not flow chrome.
 */
export function TrustBand() {
  return (
    <section
      data-testid="trust-band"
      className="bg-[radial-gradient(120%_80%_at_50%_0%,#fbf8f2,#f4f1ec_55%)] px-4 py-20 sm:px-6 sm:py-24"
    >
      <div className="mx-auto grid max-w-[1080px] gap-10 lg:grid-cols-2 lg:items-center">
        <div>
          <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
            Trust
          </div>
          <h2 className="mt-3 max-w-[18ch] font-display text-[clamp(28px,5vw,52px)] font-extrabold uppercase leading-[1] tracking-[-0.02em]">
            Every item ships with a verifiable Health Card.
          </h2>
          <p className="mt-4 max-w-[54ch] text-[15px] leading-relaxed text-ash">
            HMAC-signed, QR-scannable. The grade, the defects, the inspection
            date — anyone can verify the card is authentic and untampered. No
            account needed.
          </p>
          <ul className="mt-6 grid gap-3 text-[14px] text-ink">
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-trust" />{" "}
              <span>
                <b>Signed by ReBridge.</b> The buyer scans the QR and confirms
                authenticity in one tap.
              </span>
            </li>
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-trust" />{" "}
              <span>
                <b>Human-checked when unsure.</b> Grades below the confidence
                threshold go to the operator review console.
              </span>
            </li>
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-trust" />{" "}
              <span>
                <b>A-to-z guarantee.</b> Standard returns apply on every purchase.
              </span>
            </li>
          </ul>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/market">
              <Button variant="primary" size="md">
                Browse verified items
              </Button>
            </Link>
            <Link href="/review">
              <Button variant="secondary" size="md">
                See the review console
              </Button>
            </Link>
          </div>
        </div>

        {/* Mini Health Card */}
        <div className="rounded-card border border-hair-soft bg-pearl p-5 shadow-lg">
          <div className="flex items-center gap-2.5 border-b border-hair-soft pb-3">
            <GradeBadge grade="Good" size="md" />
            <div className="font-display text-[14px] font-bold uppercase tracking-tight">
              Running Shoes · UK 7
            </div>
            <span className="ml-auto flex items-center gap-1 font-sans text-[11px] font-bold text-trust">
              <ShieldCheck className="h-3.5 w-3.5" /> Verified
            </span>
          </div>
          <ul className="mt-3 grid gap-2 text-[12.5px]">
            <li className="flex gap-2">
              <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />
              <span>
                <b>Minor scuff</b>, left toe — cosmetic only.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-amber-deep" />
              <span>
                <b>Light wear</b>, sole — ~80% tread left.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="mt-[5px] h-[7px] w-[7px] flex-none rounded-full bg-trust" />
              <span>
                <b>Matches the original listing</b> — same item verified.
              </span>
            </li>
          </ul>
          <div className="mt-4 flex items-center gap-3 rounded-card border border-dashed border-hair p-3">
            <QrCode value="https://rebridge.app/product/itm_shoe7" size={64} />
            <div className="text-[11.5px] text-mute">
              <b className="block font-mono text-ink">RB-7F3A-91</b>
              Scan to verify · HMAC-signed
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
