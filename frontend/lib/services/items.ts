import {
  itemMetaSchema,
  presignResponseSchema,
  gradeAcceptedSchema,
  itemAggregateSchema,
  routeDecisionSchema,
  buyResponseSchema,
  cardVerificationSchema,
  type ItemAggregate,
} from "../schemas";
import { apiFetch } from "../api";
import { config } from "../config";
import { seedGradedItem } from "../seed";
import type { CreateItemInput, ItemsService } from "./types";

// ---------------------------------------------------------------------------
// LIVE — hits the real FastAPI backend (BACKEND_MAP §5).
// ---------------------------------------------------------------------------

class LiveItemsService implements ItemsService {
  readonly mode = "live" as const;

  createItem(input: CreateItemInput) {
    return apiFetch("/items", {
      method: "POST",
      body: input,
      schema: itemMetaSchema,
    });
  }
  presignPhotos(itemId: string, count: number) {
    return apiFetch(`/items/${itemId}/photos:presign`, {
      method: "POST",
      body: { count },
      schema: presignResponseSchema,
    });
  }
  enqueueGrade(itemId: string, photoKeys: string[]) {
    return apiFetch(`/items/${itemId}/grade`, {
      method: "POST",
      body: { photo_keys: photoKeys },
      schema: gradeAcceptedSchema,
    });
  }
  getItem(itemId: string) {
    return apiFetch(`/items/${itemId}`, { schema: itemAggregateSchema });
  }
  route(itemId: string, geohash5?: string) {
    return apiFetch(`/items/${itemId}/route`, {
      method: "POST",
      body: { geohash5: geohash5 ?? null },
      schema: routeDecisionSchema,
    });
  }
  createListing(input: {
    item_id: string;
    category: string;
    price: string;
    geohash5: string;
  }) {
    return apiFetch(`/listings`, { method: "POST", body: input });
  }
  buy(itemId: string) {
    return apiFetch(`/listings/${itemId}/buy`, {
      method: "POST",
      schema: buyResponseSchema,
    });
  }
  verifyCard(cardId: string, sig: string) {
    return apiFetch(`/cards/${cardId}/verify`, {
      query: { sig },
      public: true,
      schema: cardVerificationSchema,
    });
  }
}

// ---------------------------------------------------------------------------
// MOCK — in-memory store that simulates the ASYNC grade lifecycle (G6).
// getItem returns GRADING until a per-item ready-time elapses, then a real
// graded aggregate. The poll in the UI is genuine; only the data is seeded.
// ---------------------------------------------------------------------------

interface MockEntry {
  aggregate: ItemAggregate;
  gradeReadyAt: number | null; // epoch ms; null = not grading
  outcome: "GRADED" | "RETAKE_REQUIRED"; // what the next resolve becomes
}

const GRADE_LATENCY_MS = 4200; // matches the ~4.5s reveal theatre

class MockItemsService implements ItemsService {
  readonly mode = "mock" as const;
  private store = new Map<string, MockEntry>();

  private newId() {
    return "itm_" + Math.random().toString(36).slice(2, 10);
  }

    async createItem(input: CreateItemInput) {
    const item_id = input.item_id ?? this.newId();
    const meta = {
      item_id,
      status: "CREATED" as const,
      category: input.category,
      age_months: input.age_months,
      context_source: input.context_source,
      created_at: new Date().toISOString(),
      context_ref: input.order_id ?? null,
      expected_price: input.expected_price ?? null,
    };
    this.store.set(item_id, {
      aggregate: { meta, grade: null, card: null, decision: null, listing: null },
      gradeReadyAt: null,
      outcome: "GRADED",
    });
    return itemMetaSchema.parse(meta);
  }

  async presignPhotos(itemId: string, count: number) {
    return presignResponseSchema.parse({
      item_id: itemId,
      urls: Array.from({ length: count }, (_, i) => ({
        url: `https://mock-bucket.local/items/${itemId}/photo-${i + 1}`,
        method: "PUT",
        headers: {},
        expires_in: 300,
      })),
    });
  }

  async enqueueGrade(itemId: string, photoKeys: string[]) {
    const entry = this.ensure(itemId);
    // A photo key tagged "blurry" simulates a failed quality precheck (the real
    // backend returns RETAKE_REQUIRED on blur/exposure) so the retake path is
    // demoable + testable offline.
    entry.outcome = photoKeys.some((k) => k.includes("blurry"))
      ? "RETAKE_REQUIRED"
      : "GRADED";
    entry.aggregate = {
      ...entry.aggregate,
      meta: { ...entry.aggregate.meta, status: "GRADING" },
    };
    entry.gradeReadyAt = Date.now() + GRADE_LATENCY_MS;
    return gradeAcceptedSchema.parse({
      item_id: itemId,
      idempotency_key: "mock-" + photoKeys.join("|").length.toString(16),
      status: "enqueued",
    });
  }

  async getItem(itemId: string) {
    const entry = this.ensure(itemId);
    if (
      entry.gradeReadyAt !== null &&
      Date.now() >= entry.gradeReadyAt &&
      entry.aggregate.meta.status === "GRADING"
    ) {
      entry.gradeReadyAt = null;
      if (entry.outcome === "RETAKE_REQUIRED") {
        entry.aggregate = {
          ...entry.aggregate,
          meta: { ...entry.aggregate.meta, status: "RETAKE_REQUIRED" },
        };
        return itemAggregateSchema.parse(entry.aggregate);
      }
      // Transition to GRADED with a seeded grade keyed to this item.
      const seeded = seedGradedItem(itemId);
      entry.aggregate = {
        ...seeded,
        meta: {
          ...seeded.meta,
          item_id: itemId,
          category: entry.aggregate.meta.category,
          age_months: entry.aggregate.meta.age_months,
          context_source: entry.aggregate.meta.context_source,
          context_ref: entry.aggregate.meta.context_ref,
        },
        listing: entry.aggregate.listing,
      };
    }
    return itemAggregateSchema.parse(entry.aggregate);
  }

  async route(itemId: string) {
    const entry = this.ensure(itemId);
    const decision =
      entry.aggregate.decision ?? seedGradedItem(itemId).decision!;
    entry.aggregate = { ...entry.aggregate, decision };
    return routeDecisionSchema.parse(decision);
  }

  async createListing(input: {
    item_id: string;
    category: string;
    price: string;
    geohash5: string;
  }) {
    const entry = this.ensure(input.item_id);
    const listing = {
      item_id: input.item_id,
      status: "ACTIVE",
      category: input.category,
      price: input.price,
      geohash5: input.geohash5,
      listed_at: new Date().toISOString(),
    };
    entry.aggregate = {
      ...entry.aggregate,
      meta: { ...entry.aggregate.meta, status: "LISTED" },
      listing,
    };
    return listing;
  }

  async buy(itemId: string) {
    return buyResponseSchema.parse({
      item_id: itemId,
      status: "SOLD",
      order_id: Math.random().toString(16).slice(2, 12),
      simulated: true,
      message: "Simulated checkout: no payment processed. SOLD event emitted.",
    });
  }

  async verifyCard(cardId: string, sig: string) {
    const ok = sig === "RB-7F3A-91" || sig.length > 4;
    return cardVerificationSchema.parse({
      verified: ok,
      reason: ok ? "signature matches" : "presented signature does not match",
      card: ok
        ? {
            card_id: cardId,
            item_id: "itm_shoe7",
            grade: "Good",
            graded_at: "2026-06-14T09:41:00Z",
            defect_summary:
              "Matches the original listing. Observed defects: minor scuff at left toe; light wear at sole.",
            warranty_stance: "14-day returns",
            annotated_photo_keys: [],
            signature: sig,
            qr_target: `/cards/${cardId}/verify?sig=${sig}`,
          }
        : null,
    });
  }

  private ensure(itemId: string): MockEntry {
    let entry = this.store.get(itemId);
    if (!entry) {
      entry = {
        aggregate: {
          meta: {
            item_id: itemId,
            status: "CREATED",
            category: "shoes",
            age_months: 8,
            context_source: "order_scan",
            created_at: new Date().toISOString(),
            context_ref: null,
          },
          grade: null,
          card: null,
          decision: null,
          listing: null,
        },
        gradeReadyAt: null,
        outcome: "GRADED",
      };
      this.store.set(itemId, entry);
    }
    return entry;
  }
}

export const itemsService: ItemsService = config.itemsLive
  ? new LiveItemsService()
  : new MockItemsService();
