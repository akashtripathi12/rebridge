import { z } from "zod";
import { GRADES, DISPOSITIONS, ITEM_STATUSES } from "./config";

/**
 * Zod runtime schemas for every endpoint the frontend touches.
 *
 * - EXISTING endpoints mirror openapi.json field-for-field (money as string,
 *   confidence as number, timestamps as string).
 * - GAP endpoints (G1/G2/G3/G4) are hand-written to CONTRACT_ADDENDUM.md so the
 *   mock and the eventual live response validate against the identical schema.
 */

export const gradeEnum = z.enum(GRADES);
export const dispositionEnum = z.enum(DISPOSITIONS);
export const itemStatusEnum = z.enum(ITEM_STATUSES);
const money = z.string(); // never compute on this
const intentTier = z.enum(["HIGH", "MEDIUM", "LOW"]);
const priorityTier = z.enum(["HIGH", "MEDIUM", "LOW"]);

// ---------------------------------------------------------------------------
// EXISTING — items / grading / routing / listings / cards (openapi.json)
// ---------------------------------------------------------------------------

export const itemMetaSchema = z.object({
  item_id: z.string(),
  status: itemStatusEnum,
  category: z.string(),
  age_months: z.number(),
  context_source: z.string(),
  created_at: z.string(),
  context_ref: z.string().nullable().optional(),
  expected_price: z.number().nullable().optional(),
});

export const defectSchema = z.object({
  location: z.string(),
  severity: z.string(),
});

export const completenessSchema = z.object({
  complete: z.boolean(),
  missing_components: z.array(z.string()),
});

export const gradeFacetSchema = z.object({
  grade: z.string(),
  confidence: z.number(),
  summary: z.string(),
  defects: z.array(defectSchema),
  completeness: completenessSchema.nullable().optional(),
  idem_key: z.string().nullable().optional(),
  confirmed: z.boolean(),
});

export const cardFacetSchema = z.object({
  card_id: z.string(),
  item_id: z.string(),
  signature: z.string(),
  qr_target: z.string(),
  graded_at: z.string(),
  warranty_stance: z.string(),
  annotated_photo_keys: z.array(z.string()),
});

export const decisionFacetSchema = z.object({
  disposition: z.string(),
  price: money,
  value: money,
  cost: money,
  margin: money,
  rationale: z.string(),
  // G4 fold-in: present once backend adds it; optional until then.
  price_new: money.nullable().optional(),
});

export const listingFacetSchema = z.object({
  item_id: z.string(),
  status: z.string(),
  category: z.string(),
  price: money,
  geohash5: z.string(),
  listed_at: z.string(),
});

export const itemAggregateSchema = z.object({
  meta: itemMetaSchema,
  grade: gradeFacetSchema.nullable().optional(),
  card: cardFacetSchema.nullable().optional(),
  decision: decisionFacetSchema.nullable().optional(),
  listing: listingFacetSchema.nullable().optional(),
});

export const presignedUrlSchema = z.object({
  url: z.string(),
  method: z.string(),
  headers: z.record(z.string()),
  expires_in: z.number(),
});
export const presignResponseSchema = z.object({
  item_id: z.string(),
  urls: z.array(presignedUrlSchema),
});

export const gradeAcceptedSchema = z.object({
  item_id: z.string(),
  idempotency_key: z.string(),
  status: z.string().optional(),
});

export const routeDecisionSchema = decisionFacetSchema;

export const buyResponseSchema = z.object({
  item_id: z.string(),
  status: z.string(),
  order_id: z.string(),
  simulated: z.boolean(),
  message: z.string(),
});

export const cardVerificationSchema = z.object({
  verified: z.boolean(),
  card: z
    .object({
      card_id: z.string(),
      item_id: z.string(),
      grade: z.string(),
      graded_at: z.string(),
      defect_summary: z.string(),
      warranty_stance: z.string(),
      annotated_photo_keys: z.array(z.string()),
      signature: z.string(),
      qr_target: z.string(),
    })
    .nullable(),
  reason: z.string(),
});

// ---------------------------------------------------------------------------
// G1 — matching (GET /items/{id}/matches)
// ---------------------------------------------------------------------------

export const matchSchema = z.object({
  buyer_id: z.string(),
  display_label: z.string(),
  distance_km: z.number(),
  match_score: z.number(),
  match_reasons: z.array(z.string()),
  intent_tier: intentTier,
});
export const matchesResponseSchema = z.object({
  item_id: z.string(),
  generated_at: z.string(),
  matches: z.array(matchSchema),
  match_count_within_5km: z.number(),
  top_reason: z.string().nullable(),
});

// ---------------------------------------------------------------------------
// G2 — review queue (GET /review/queue, POST /review/{id})
// ---------------------------------------------------------------------------

export const reviewQueueItemSchema = z.object({
  item_id: z.string(),
  title: z.string(),
  ai_grade: gradeEnum,
  confidence: z.number(),
  est_value: money,
  priority: priorityTier,
  photo_keys: z.array(z.string()),
  created_at: z.string(),
});
export const reviewQueueResponseSchema = z.object({
  queue: z.array(reviewQueueItemSchema),
  total: z.number(),
});
export const reviewActionSchema = z.object({
  action: z.enum(["CONFIRM", "OVERRIDE"]),
  override_grade: gradeEnum.nullable(),
});

// ---------------------------------------------------------------------------
// G3/G4 — extended marketplace item (GET /marketplace)
// ---------------------------------------------------------------------------

export const marketplaceItemSchema = z.object({
  listing_id: z.string(),
  item_id: z.string(),
  title: z.string(),
  grade: gradeEnum.nullable().optional(),
  distance_km: z.number(),
  price: money,
  price_new: money,
  health_card_id: z.string().nullable().optional(),
  category: z.string(),
  thumb_key: z.string(),
});
export const marketplaceResponseSchema = z.object({
  listings: z.array(marketplaceItemSchema),
});

// ---------------------------------------------------------------------------
// Health Card view-model — composed client-side from the EXISTING public verify
// endpoint (GET /cards/{id}/verify) + the item grade facet (GET /items/{id}).
// Not a new wire contract; both sources are already Zod-validated above.
// ---------------------------------------------------------------------------

export const healthCardViewSchema = z.object({
  card_id: z.string(),
  item_id: z.string(),
  title: z.string(),
  grade: gradeEnum,
  confidence: z.number(),
  defects: z.array(defectSchema),
  warranty_stance: z.string(),
  graded_at: z.string(),
  signature: z.string(),
  qr_target: z.string(),
  verified: z.boolean(),
  price: money,
  price_new: money,
  thumb_key: z.string(),
  images: z.array(z.string()).optional(),
});

// ---------------------------------------------------------------------------
// Inferred types
// ---------------------------------------------------------------------------

export type ItemMeta = z.infer<typeof itemMetaSchema>;
export type GradeFacet = z.infer<typeof gradeFacetSchema>;
export type CardFacet = z.infer<typeof cardFacetSchema>;
export type DecisionFacet = z.infer<typeof decisionFacetSchema>;
export type ListingFacet = z.infer<typeof listingFacetSchema>;
export type ItemAggregate = z.infer<typeof itemAggregateSchema>;
export type PresignResponse = z.infer<typeof presignResponseSchema>;
export type GradeAccepted = z.infer<typeof gradeAcceptedSchema>;
export type RouteDecision = z.infer<typeof routeDecisionSchema>;
export type BuyResponse = z.infer<typeof buyResponseSchema>;
export type CardVerification = z.infer<typeof cardVerificationSchema>;
export type Match = z.infer<typeof matchSchema>;
export type MatchesResponse = z.infer<typeof matchesResponseSchema>;
export type ReviewQueueItem = z.infer<typeof reviewQueueItemSchema>;
export type ReviewQueueResponse = z.infer<typeof reviewQueueResponseSchema>;
export type ReviewAction = z.infer<typeof reviewActionSchema>;
export type MarketplaceItem = z.infer<typeof marketplaceItemSchema>;
export type MarketplaceResponse = z.infer<typeof marketplaceResponseSchema>;
export type HealthCardView = z.infer<typeof healthCardViewSchema>;
