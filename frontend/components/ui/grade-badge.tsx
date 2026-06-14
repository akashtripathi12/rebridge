import { cn } from "@/lib/utils";

/**
 * GradeBadge — uppercase Archivo on a BLACK chip (v2: grade badges are ink, not
 * amber). The grade label is rendered verbatim from the backend enum.
 */
export function GradeBadge({
  grade,
  size = "md",
  className,
}: {
  grade: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizes: Record<string, string> = {
    sm: "text-[8.5px] px-1.5 py-0.5 rounded",
    md: "text-[12px] px-3 py-1 rounded-lg",
    lg: "text-[14px] px-3.5 py-1.5 rounded-lg",
  };
  return (
    <span
      data-grade-badge
      className={cn(
        "inline-block bg-ink font-display font-extrabold uppercase tracking-[0.04em] text-white",
        sizes[size],
        className,
      )}
    >
      {grade}
    </span>
  );
}
