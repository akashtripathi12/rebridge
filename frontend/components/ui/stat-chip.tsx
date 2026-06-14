import { cn } from "@/lib/utils";

/**
 * StatChip — a small labelled value chip (e.g. order context, CO₂e saved,
 * pickup slot). Numbers inside use mono via the .tnum on the value.
 */
export function StatChip({
  label,
  value,
  tone = "default",
  className,
}: {
  label: string;
  value: string;
  tone?: "default" | "trust" | "dark";
  className?: string;
}) {
  const tones: Record<string, string> = {
    default: "bg-paper border border-hair text-ash",
    trust: "bg-[#E7F4EC] border border-transparent text-trust",
    dark: "bg-white/10 border border-white/15 text-white",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill px-3 py-1.5 font-sans text-[11px] font-semibold",
        tones[tone],
        className,
      )}
    >
      <span className="text-mute">{label}</span>
      <span className="tnum text-ink data-[tone=dark]:text-white">{value}</span>
    </span>
  );
}
