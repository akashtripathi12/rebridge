import { cn } from "@/lib/utils";
import { formatMoney, percentSaved } from "@/lib/format";

/**
 * Price — THE one place amber lives. Renders a money string (never computes on
 * it) in Archivo display + amber-deep, the brightest thing on the screen.
 * Optional `priceNew` shows the struck-through "new" price + % saved (G4).
 */
export function Price({
  value,
  priceNew,
  size = "md",
  className,
  "data-testid": testId,
}: {
  value: string | null | undefined;
  priceNew?: string | null;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
  "data-testid"?: string;
}) {
  const sizes: Record<string, string> = {
    sm: "text-[13px]",
    md: "text-[18px]",
    lg: "text-[26px]",
    xl: "text-[44px]",
  };
  const saved = percentSaved(value, priceNew);
  return (
    <span className={cn("inline-flex items-baseline gap-2", className)}>
      <span
        data-price="amber"
        data-testid={testId}
        className={cn(
          "font-display font-extrabold tracking-[-0.01em] text-amber-deep",
          sizes[size],
        )}
      >
        {formatMoney(value)}
      </span>
      {priceNew ? (
        <span className="tnum text-[12px] font-medium text-stone line-through">
          {formatMoney(priceNew)}
        </span>
      ) : null}
      {saved ? (
        <span className="tnum text-[11px] font-semibold text-trust">
          save {saved}%
        </span>
      ) : null}
    </span>
  );
}
