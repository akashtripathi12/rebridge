import { cn } from "@/lib/utils";

/**
 * DarkStage — the dark editorial product stage (radial charcoal → near-black)
 * with a giant ghosted wordmark behind the product. This is the mount point for
 * the 3D scanner / Higgsfield shots; everywhere else it frames a ProductGlyph.
 */
export function DarkStage({
  children,
  ghost = "RB",
  className,
  rounded = "rounded-[26px]",
}: {
  children: React.ReactNode;
  ghost?: string;
  className?: string;
  rounded?: string;
}) {
  return (
    <div
      className={cn(
        "relative flex items-center justify-center overflow-hidden bg-stage-dark",
        rounded,
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center font-display text-[130px] font-black uppercase leading-none tracking-[-0.04em] text-white/[0.045]">
        {ghost}
      </div>
      {children}
    </div>
  );
}
