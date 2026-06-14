"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GradeBadge } from "@/components/ui/grade-badge";
import { PriorityTag } from "@/components/ui/priority-tag";
import { Button } from "@/components/ui/button";
import { reviewService } from "@/lib/services";
import { formatMoney, formatPercent } from "@/lib/format";
import {
  priorityFor,
  priorityRank,
  OVERRIDE_GRADES,
  type Priority,
} from "@/lib/review/thresholds";
import type { ReviewQueueItem } from "@/lib/schemas";
import { ImageIcon } from "lucide-react";

type Resolution = { action: "CONFIRM" | "OVERRIDE" | "RETAKE"; grade?: string };

/**
 * ReviewConsole — the human-in-the-loop. Low-confidence grades queued by
 * priority (computed from confidence via thresholds.ts — single source), each
 * row showing the item, AI grade + confidence, captured-photo count, and
 * approve / override / request-retake. Calm dense desktop table (no GSAP/3D in
 * operator tools). Every override trains the model — that's the trust story.
 */
export function ReviewConsole() {
  const queue = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => reviewService.getQueue(),
  });
  const [resolved, setResolved] = useState<Record<string, Resolution>>({});
  const [overrideSel, setOverrideSel] = useState<Record<string, string>>({});

  const rows = useMemo(() => {
    const items = queue.data?.queue ?? [];
    // Priority from confidence (thresholds.ts), then most-uncertain first.
    return [...items].sort((a, b) => {
      const pa = priorityFor(a.confidence);
      const pb = priorityFor(b.confidence);
      return priorityRank(pa) - priorityRank(pb) || a.confidence - b.confidence;
    });
  }, [queue.data]);

  const act = async (item: ReviewQueueItem, action: Resolution["action"]) => {
    const grade =
      action === "OVERRIDE" ? (overrideSel[item.item_id] ?? item.ai_grade) : undefined;
    await reviewService.act(item.item_id, {
      action: action === "RETAKE" ? "CONFIRM" : action,
      override_grade: action === "OVERRIDE" ? (grade as never) : null,
    });
    setResolved((r) => ({ ...r, [item.item_id]: { action, grade } }));
  };

  const pending = rows.filter((r) => !resolved[r.item_id]).length;

  return (
    <div className="overflow-hidden rounded-card border border-hair bg-canvas shadow-lg">
      {/* window chrome */}
      <div className="flex gap-1.5 bg-ink/[0.92] px-3 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-sale" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber" />
        <span className="h-2.5 w-2.5 rounded-full bg-trust" />
      </div>
      <div className="flex items-center gap-3 border-b border-hair bg-paper px-5 py-3.5">
        <h2 className="font-display text-[16px] font-extrabold uppercase tracking-tight">
          Review Console
        </h2>
        <span className="ml-auto tnum text-[11px] text-mute">
          Queue: {pending} · sorted by value × uncertainty
        </span>
      </div>

      <table className="w-full border-collapse" data-testid="review-table">
        <thead>
          <tr>
            {["Item", "Photos", "AI grade", "Conf.", "Est. value", "Priority", "Action"].map(
              (h) => (
                <th
                  key={h}
                  className="border-b border-hair bg-paper px-4 py-2.5 text-left font-sans text-[10px] font-bold uppercase tracking-[0.07em] text-mute"
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => {
            const p: Priority = priorityFor(item.confidence);
            const res = resolved[item.item_id];
            return (
              <tr
                key={item.item_id}
                data-testid="review-row"
                data-item={item.item_id}
                data-resolved={res ? res.action : ""}
                className={res ? "opacity-55" : ""}
              >
                <td className="border-b border-hair px-4 py-3 text-[12.5px] font-medium">
                  {item.title}
                </td>
                <td className="border-b border-hair px-4 py-3">
                  <span className="tnum inline-flex items-center gap-1 rounded-md border border-hair bg-paper px-2 py-1 text-[10px] text-mute">
                    <ImageIcon className="h-3 w-3" /> {item.photo_keys.length}
                  </span>
                </td>
                <td className="border-b border-hair px-4 py-3">
                  {res?.action === "OVERRIDE" ? (
                    <span className="flex items-center gap-1.5">
                      <span className="tnum text-[11px] text-stone line-through">
                        {item.ai_grade}
                      </span>
                      <GradeBadge grade={res.grade ?? item.ai_grade} size="sm" />
                    </span>
                  ) : (
                    <span className="tnum text-[12px]">{item.ai_grade}</span>
                  )}
                </td>
                <td className="border-b border-hair px-4 py-3 tnum text-[12px]">
                  {formatPercent(item.confidence)}
                </td>
                <td className="border-b border-hair px-4 py-3 tnum text-[12px]">
                  {formatMoney(item.est_value)}
                </td>
                <td className="border-b border-hair px-4 py-3">
                  <PriorityTag priority={p} />
                </td>
                <td className="border-b border-hair px-4 py-3">
                  {res ? (
                    <span
                      data-testid="row-resolution"
                      className="tnum text-[11px] font-semibold text-trust"
                    >
                      {res.action === "CONFIRM"
                        ? "Confirmed → GRADED"
                        : res.action === "OVERRIDE"
                          ? `Overridden → ${res.grade}`
                          : "Retake requested"}
                    </span>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="primary"
                        data-testid="confirm-btn"
                        onClick={() => act(item, "CONFIRM")}
                        className="px-3 py-1.5 text-[11px]"
                      >
                        Confirm
                      </Button>
                      <select
                        data-testid="override-select"
                        value={overrideSel[item.item_id] ?? item.ai_grade}
                        onChange={(e) =>
                          setOverrideSel((s) => ({
                            ...s,
                            [item.item_id]: e.target.value,
                          }))
                        }
                        className="rounded-md border border-hair bg-white px-1.5 py-1.5 text-[11px]"
                      >
                        {OVERRIDE_GRADES.map((g) => (
                          <option key={g} value={g}>
                            {g}
                          </option>
                        ))}
                      </select>
                      <Button
                        size="sm"
                        variant="secondary"
                        data-testid="override-btn"
                        onClick={() => act(item, "OVERRIDE")}
                        className="px-3 py-1.5 text-[11px]"
                      >
                        Override
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        data-testid="retake-btn"
                        onClick={() => act(item, "RETAKE")}
                        className="px-2 py-1.5 text-[11px]"
                      >
                        Retake
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="border-t border-hair bg-paper px-5 py-2.5 text-[11px] text-mute">
        Every override trains the model · a human double-checks low scores.
      </div>
    </div>
  );
}
