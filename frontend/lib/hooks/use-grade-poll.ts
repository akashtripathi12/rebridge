"use client";

import { useQuery } from "@tanstack/react-query";
import { itemsService } from "@/lib/services";
import { GRADING_TERMINAL } from "@/lib/config";
import type { ItemAggregate } from "@/lib/schemas";

/**
 * G6 — poll GET /items/{id} every ~1.5s until meta.status leaves GRADING.
 * Terminal states stop the poll. Returns the aggregate + a derived `terminal`
 * flag the reveal uses to switch from "scanning" to the staged reveal.
 */
export function useGradePoll(itemId: string | null) {
  const query = useQuery<ItemAggregate>({
    queryKey: ["item", itemId],
    enabled: !!itemId,
    queryFn: () => itemsService.getItem(itemId as string),
    refetchInterval: (q) => {
      const status = q.state.data?.meta.status;
      if (status && GRADING_TERMINAL.includes(status)) return false;
      return 1500;
    },
  });

  const status = query.data?.meta.status ?? null;
  const terminal = status ? GRADING_TERMINAL.includes(status) : false;
  return { ...query, status, terminal };
}
