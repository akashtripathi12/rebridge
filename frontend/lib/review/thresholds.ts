import type { GradeLabel } from "@/lib/config";

/**
 * G2 assumption (until backend confirms): priority buckets from grade confidence.
 *   HIGH  : confidence < 0.70
 *   MEDIUM: 0.70 ≤ confidence < 0.85
 *   LOW   : confidence ≥ 0.85
 * SINGLE source of truth — confirming the real cutoffs is a one-line change here.
 * Documented in FOR_BACKEND.md.
 */
export const PRIORITY_THRESHOLDS = { high: 0.7, med: 0.85 } as const;

export type Priority = "HIGH" | "MEDIUM" | "LOW";

export function priorityFor(confidence: number): Priority {
  if (confidence < PRIORITY_THRESHOLDS.high) return "HIGH";
  if (confidence < PRIORITY_THRESHOLDS.med) return "MEDIUM";
  return "LOW";
}

/** Sort key: HIGH first, then by uncertainty (lower confidence = more urgent). */
export function priorityRank(p: Priority): number {
  return { HIGH: 0, MEDIUM: 1, LOW: 2 }[p];
}

/** The grade options a reviewer can override to (verbatim enum). */
export const OVERRIDE_GRADES: GradeLabel[] = [
  "Like New",
  "Very Good",
  "Good",
  "Acceptable",
  "Unsellable",
];
