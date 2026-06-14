import type {
  MarketplaceItem,
  MatchesResponse,
  ReviewQueueItem,
  ItemAggregate,
  Match,
  HealthCardView,
} from "./schemas";

/**
 * Seeded demo data. Mirrors the products in rebridge_design_reference_v2.html so
 * the mock services feel real. Money is a string everywhere (contract rule).
 * The FOR_BACKEND.md note quotes these byte-for-byte so the backend can match.
 */

export const SEED_MARKETPLACE: MarketplaceItem[] = [
  {
    listing_id: "lst_shoe7",
    item_id: "itm_shoe7",
    title: "Running Shoes · UK 7",
    grade: "Good",
    distance_km: 4.0,
    price: "340.00",
    price_new: "500.00",
    health_card_id: "card_shoe7",
    category: "shoes",
    thumb_key: "shoe",
  },
  {
    listing_id: "lst_mx2",
    item_id: "itm_mx2",
    title: "Baby Monitor · MX-2",
    grade: "Very Good",
    distance_km: 2.0,
    price: "1450.00",
    price_new: "3299.00",
    health_card_id: "card_mx2",
    category: "baby",
    thumb_key: "monitor",
  },
  {
    listing_id: "lst_buds",
    item_id: "itm_buds",
    title: "Wireless Earbuds",
    grade: "Good",
    distance_km: 6.0,
    price: "799.00",
    price_new: "1999.00",
    health_card_id: "card_buds",
    category: "tech",
    thumb_key: "earbuds",
  },
  {
    listing_id: "lst_gate",
    item_id: "itm_gate",
    title: "GATE Prep Set (4)",
    grade: "Like New",
    distance_km: 1.0,
    price: "520.00",
    price_new: "1200.00",
    health_card_id: "card_gate",
    category: "books",
    thumb_key: "books",
  },
];

const MATCH_POOL: Match[] = [
  {
    buyer_id: "buy_001",
    display_label: "Buyer 2 km away",
    distance_km: 2.0,
    match_score: 0.94,
    match_reasons: ["wishlisted this product", "recent stroller purchase"],
    intent_tier: "HIGH",
  },
  {
    buyer_id: "buy_002",
    display_label: "Buyer 4 km away",
    distance_km: 4.0,
    match_score: 0.88,
    match_reasons: ["browsing this category", "deal-seeker"],
    intent_tier: "HIGH",
  },
  {
    buyer_id: "buy_003",
    display_label: "Buyer 5 km away",
    distance_km: 4.6,
    match_score: 0.72,
    match_reasons: ["price-sensitive shopper nearby"],
    intent_tier: "MEDIUM",
  },
  {
    buyer_id: "buy_004",
    display_label: "Buyer 8 km away",
    distance_km: 8.1,
    match_score: 0.55,
    match_reasons: ["category match"],
    intent_tier: "LOW",
  },
];

/**
 * Per-item match flavour so each marketplace card reads distinctly (deterministic
 * for the demo). Falls back to the generic pool for unknown items.
 */
const ITEM_MATCH_META: Record<
  string,
  { reason: string; count: number; score: number }
> = {
  itm_shoe7: { reason: "wishlisted these", count: 3, score: 0.94 },
  itm_mx2: { reason: "recent baby-gear purchase", count: 4, score: 0.91 },
  itm_buds: { reason: "browsing audio nearby", count: 2, score: 0.86 },
  itm_gate: { reason: "exam-prep shopper nearby", count: 5, score: 0.97 },
};

/** Build a MatchesResponse for an item (deterministic, varies per item id). */
export function seedMatches(itemId: string): MatchesResponse {
  const meta = ITEM_MATCH_META[itemId];
  const top: Match = meta
    ? { ...MATCH_POOL[0], match_score: meta.score, match_reasons: [meta.reason] }
    : MATCH_POOL[0];
  const matches = [top, ...MATCH_POOL.slice(1)];
  const within5 = meta?.count ?? matches.filter((m) => m.distance_km <= 5).length;
  return {
    item_id: itemId,
    generated_at: new Date().toISOString(),
    matches,
    match_count_within_5km: within5,
    top_reason: matches[0]?.match_reasons[0] ?? null,
  };
}

export const SEED_REVIEW_QUEUE: ReviewQueueItem[] = [
  {
    item_id: "itm_mixer",
    title: "Mixer grinder · 750W",
    ai_grade: "Good",
    confidence: 0.64,
    est_value: "1900.00",
    priority: "HIGH",
    photo_keys: ["uploads/itm_mixer/0.jpg"],
    created_at: "2026-06-14T08:40:00Z",
  },
  {
    item_id: "itm_cycle",
    title: 'Kids cycle · 16"',
    ai_grade: "Acceptable",
    confidence: 0.71,
    est_value: "1200.00",
    priority: "HIGH",
    photo_keys: ["uploads/itm_cycle/0.jpg"],
    created_at: "2026-06-14T08:44:00Z",
  },
  {
    item_id: "itm_case",
    title: "Phone case (handmade)",
    ai_grade: "Like New",
    confidence: 0.77,
    est_value: "240.00",
    priority: "MEDIUM",
    photo_keys: ["uploads/itm_case/0.jpg"],
    created_at: "2026-06-14T08:51:00Z",
  },
];

/**
 * A fully graded aggregate for the demo reveal / health card (the "Running
 * Shoes" hero item). Matches the rebridge_ui_v2 reveal content.
 */
export function seedGradedItem(itemId = "itm_shoe7"): ItemAggregate {
  return {
    meta: {
      item_id: itemId,
      status: "GRADED",
      category: "shoes",
      age_months: 8,
      context_source: "order_scan",
      created_at: "2026-06-14T09:40:00Z",
      context_ref: "AMZ-7F3A",
    },
    grade: {
      grade: "Good",
      confidence: 0.91,
      summary: "Matches the original listing. Cosmetic wear only.",
      defects: [
        { location: "left toe", severity: "minor scuff" },
        { location: "sole", severity: "light wear" },
      ],
      completeness: { complete: false, missing_components: ["box"] },
      idem_key: "seed",
      confirmed: false,
    },
    card: {
      card_id: "card_shoe7",
      item_id: itemId,
      signature: "RB-7F3A-91",
      qr_target: "/cards/card_shoe7/verify?sig=RB-7F3A-91",
      graded_at: "2026-06-14T09:41:00Z",
      warranty_stance: "14-day returns",
      annotated_photo_keys: [],
    },
    decision: {
      disposition: "P2P",
      price: "340.00",
      value: "340.00",
      cost: "110.00",
      margin: "230.00",
      rationale:
        "P2P selected: highest-margin viable path (recovered value ₹340, handling cost ₹110, margin ₹230).",
      price_new: "500.00",
    },
    listing: null,
  };
}

/**
 * Per-item grade detail (confidence + defects + warranty + signature) that the
 * Health Card composes with the marketplace fields. In live mode this comes from
 * GET /items/{id} (confidence, defects) + GET /cards/{id}/verify (warranty,
 * signature, verified).
 */
const ITEM_GRADE_DETAIL: Record<
  string,
  {
    confidence: number;
    defects: { location: string; severity: string }[];
    warranty: string;
    graded_at: string;
    signature: string;
  }
> = {
  itm_shoe7: {
    confidence: 0.91,
    defects: [
      { location: "left toe", severity: "minor scuff" },
      { location: "sole", severity: "light wear" },
    ],
    warranty: "14-day returns",
    graded_at: "2026-06-14T09:41:00Z",
    signature: "RB-7F3A-91",
  },
  itm_mx2: {
    confidence: 0.94,
    defects: [{ location: "screen", severity: "faint scratch" }],
    warranty: "30-day returns",
    graded_at: "2026-06-14T09:12:00Z",
    signature: "RB-2B8C-94",
  },
  itm_buds: {
    confidence: 0.82,
    defects: [
      { location: "left bud", severity: "ear-tip wear" },
      { location: "case hinge", severity: "light scuff" },
    ],
    warranty: "14-day returns",
    graded_at: "2026-06-14T08:55:00Z",
    signature: "RB-9D4E-82",
  },
  itm_gate: {
    confidence: 0.97,
    defects: [],
    warranty: "30-day returns",
    graded_at: "2026-06-14T08:30:00Z",
    signature: "RB-5A1F-97",
  },
};

/** Compose a Health Card view-model by item_id OR health_card_id. */
export function seedHealthCard(idOrCardId: string): HealthCardView | null {
  const item = SEED_MARKETPLACE.find(
    (m) => m.item_id === idOrCardId || m.health_card_id === idOrCardId,
  );
  if (!item) return null;
  const d = ITEM_GRADE_DETAIL[item.item_id] ?? ITEM_GRADE_DETAIL.itm_shoe7;
  return {
    card_id: item.health_card_id,
    item_id: item.item_id,
    title: item.title,
    grade: item.grade,
    confidence: d.confidence,
    defects: d.defects,
    warranty_stance: d.warranty,
    graded_at: d.graded_at,
    signature: d.signature,
    qr_target: `/cards/${item.health_card_id}/verify?sig=${d.signature}`,
    verified: true,
    price: item.price,
    price_new: item.price_new,
    thumb_key: item.thumb_key,
  };
}
