import { cn } from "@/lib/utils";

/**
 * StatusLine — the staged status copy during AI work (no wordless spinners).
 * Amber pulsing dot while working; turns trust-green + solid when done.
 */
export function StatusLine({
  text,
  done = false,
  className,
}: {
  text: string;
  done?: boolean;
  className?: string;
}) {
  return (
    <div
      data-testid="status-line"
      data-done={done}
      className={cn("flex min-h-[26px] items-center gap-2.5", className)}
    >
      <span
        className={cn(
          "h-[7px] w-[7px] rounded-full",
          done ? "bg-trust" : "animate-pulse2 bg-amber",
        )}
      />
      <span
        className={cn(
          "font-sans text-[13px]",
          done ? "font-semibold text-trust" : "font-medium text-ash",
        )}
      >
        {text}
      </span>
    </div>
  );
}
