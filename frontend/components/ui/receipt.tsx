import { cn } from "@/lib/utils";

export type ReceiptRow =
  | { kind: "line"; label: string; value: string; muted?: boolean }
  | { kind: "rule" }
  | { kind: "total"; label: string; value: string }
  | { kind: "route"; label: string; value: string };

/**
 * Receipt — the disposition economics, printed in mono like a receipt. Rows can
 * be progressively revealed (Phase 3 theatre) via `revealed` (count of rows
 * shown); omit it to show all. Margin total is trust-green; the route value is
 * the disposition emphasis (amber-deep, per the v2 reference).
 */
export function Receipt({
  rows,
  revealed,
  title = "Disposition economics",
  className,
}: {
  rows: ReceiptRow[];
  revealed?: number;
  title?: string;
  className?: string;
}) {
  const shownCount = revealed ?? rows.length;
  return (
    <div
      data-testid="receipt"
      className={cn(
        "rounded-2xl border border-hair bg-paper px-4 py-3.5",
        className,
      )}
    >
      <div className="mb-2 font-sans text-[10px] font-bold uppercase tracking-[0.16em] text-stone">
        {title}
      </div>
      <div className="flex flex-col">
        {rows.map((row, i) => {
          const show = i < shownCount;
          const base = cn(
            "transition-all duration-300 ease-out",
            show ? "translate-y-0 opacity-100" : "translate-y-[3px] opacity-0",
          );
          if (row.kind === "rule") {
            return (
              <div
                key={i}
                className={cn("my-[7px] border-t border-dashed border-hair", base)}
              />
            );
          }
          const value =
            row.kind === "total" ? (
              <b className="font-semibold text-trust">{row.value}</b>
            ) : row.kind === "route" ? (
              <b className="font-semibold text-amber-deep">{row.value}</b>
            ) : (
              <span>{row.value}</span>
            );
          return (
            <div
              key={i}
              data-receipt-row
              className={cn(
                "flex justify-between py-[3px] tnum text-[13px] font-medium",
                row.kind === "line" && row.muted ? "text-mute" : "text-ink",
                row.kind === "route" && "font-semibold",
                base,
              )}
            >
              <span className="font-sans font-medium">{row.label}</span>
              {value}
            </div>
          );
        })}
      </div>
    </div>
  );
}
