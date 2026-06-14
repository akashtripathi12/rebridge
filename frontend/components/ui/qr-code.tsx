"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

/**
 * A REAL QR (encodes `value`, scannable) rendered as inline SVG. Used on the
 * Health Card so the code actually resolves to the card's verifiable URL — no
 * decorative fakes (capability-honesty rule).
 */
export function QrCode({
  value,
  size = 76,
  className,
}: {
  value: string;
  size?: number;
  className?: string;
}) {
  const [svg, setSvg] = useState("");
  useEffect(() => {
    QRCode.toString(value, {
      type: "svg",
      margin: 0,
      errorCorrectionLevel: "M",
      color: { dark: "#111111", light: "#00000000" },
    })
      .then(setSvg)
      .catch(() => setSvg(""));
  }, [value]);
  return (
    <div
      data-testid="qr"
      data-qr-value={value}
      style={{ width: size, height: size }}
      className={className}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
