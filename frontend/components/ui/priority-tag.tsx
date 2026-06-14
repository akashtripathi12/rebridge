import { cn } from "@/lib/utils";

/** PriorityTag — review-queue priority (HIGH/MED/LOW). Sale-red for HIGH. */
export function PriorityTag({
  priority,
  className,
}: {
  priority: "HIGH" | "MEDIUM" | "LOW";
  className?: string;
}) {
  const styles: Record<string, string> = {
    HIGH: "bg-[#FCE9E9] text-sale",
    MEDIUM: "bg-[#FFF2DF] text-amber-deep",
    LOW: "bg-hair text-ash",
  };
  const label = { HIGH: "High", MEDIUM: "Med", LOW: "Low" }[priority];
  return (
    <span
      data-testid="priority-tag"
      className={cn(
        "inline-block rounded-[5px] px-2 py-[3px] font-sans text-[9.5px] font-bold uppercase",
        styles[priority],
        className,
      )}
    >
      {label}
    </span>
  );
}
