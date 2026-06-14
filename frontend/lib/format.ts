/**
 * Money & number formatting. CRITICAL CONTRACT RULE: money arrives as a JSON
 * string ("340.00"). We FORMAT it for display — we never do arithmetic on it.
 * The only "math" allowed is the % saved helper, which derives a ratio for a
 * label, never a money value to send back.
 */

const inr = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0,
});

/** "340.00" -> "₹340" (Indian digit grouping, no paise for display). */
export function formatMoney(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `₹${inr.format(Math.round(n))}`;
}

/** Signed money for receipt deltas: "-110" -> "−₹110", "230" -> "+₹230". */
export function formatSignedMoney(value: string | number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const sign = n < 0 ? "−" : "+";
  return `${sign}₹${inr.format(Math.abs(Math.round(n)))}`;
}

/** 0.91 -> "91%". confidence is a NUMBER on the wire. */
export function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

/**
 * "% saved" label from price vs price_new. Both are strings; this returns a
 * display-only integer percent. Returns null when not derivable.
 */
export function percentSaved(
  price: string | null | undefined,
  priceNew: string | null | undefined,
): number | null {
  if (!price || !priceNew) return null;
  const p = Number(price);
  const pn = Number(priceNew);
  if (!Number.isFinite(p) || !Number.isFinite(pn) || pn <= 0) return null;
  const pct = Math.round((1 - p / pn) * 100);
  return pct > 0 ? pct : null;
}

/** "4.2" km -> "4 km" (whole km is how the design shows distance). */
export function formatDistance(km: number | null | undefined): string {
  if (km == null || !Number.isFinite(km)) return "—";
  return `${Math.round(km)} km`;
}
