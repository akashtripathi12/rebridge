import {
  reviewQueueResponseSchema,
  itemAggregateSchema,
  type ReviewAction,
  type ReviewQueueItem,
} from "../schemas";
import { apiFetch } from "../api";
import { config } from "../config";
import { SEED_REVIEW_QUEUE } from "../seed";
import type { ReviewService } from "./types";

// G2 — GET /review/queue + POST /review/{id} (backend to add).
class LiveReviewService implements ReviewService {
  readonly mode = "live" as const;
  getQueue() {
    return apiFetch(`/review/queue`, { schema: reviewQueueResponseSchema });
  }
  act(itemId: string, action: ReviewAction) {
    return apiFetch(`/review/${itemId}`, {
      method: "POST",
      body: action,
      schema: itemAggregateSchema,
    });
  }
}

class MockReviewService implements ReviewService {
  readonly mode = "mock" as const;
  private queue: ReviewQueueItem[] = [...SEED_REVIEW_QUEUE];

  async getQueue() {
    return reviewQueueResponseSchema.parse({
      queue: this.queue,
      total: this.queue.length,
    });
  }
  async act(itemId: string, action: ReviewAction) {
    const entry = this.queue.find((q) => q.item_id === itemId);
    this.queue = this.queue.filter((q) => q.item_id !== itemId);
    const grade =
      action.action === "OVERRIDE" && action.override_grade
        ? action.override_grade
        : (entry?.ai_grade ?? "Good");
    return itemAggregateSchema.parse({
      meta: {
        item_id: itemId,
        status: "GRADED",
        category: "home",
        age_months: 12,
        context_source: "manual",
        created_at: entry?.created_at ?? new Date().toISOString(),
        context_ref: null,
      },
      grade: {
        grade,
        confidence: entry?.confidence ?? 0.9,
        summary: "Human-reviewed.",
        defects: [],
        completeness: { complete: true, missing_components: [] },
        idem_key: null,
        confirmed: true,
      },
      card: null,
      decision: null,
      listing: null,
    });
  }
}

export const reviewService: ReviewService = config.reviewLive
  ? new LiveReviewService()
  : new MockReviewService();
