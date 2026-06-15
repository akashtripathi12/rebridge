import type {
  ItemAggregate,
  ItemMeta,
  PresignResponse,
  GradeAccepted,
  RouteDecision,
  BuyResponse,
  CardVerification,
  MatchesResponse,
  ReviewQueueResponse,
  MarketplaceResponse,
  ReviewAction,
  HealthCardView,
} from "../schemas";

export interface CreateItemInput {
  context_source: "order_scan" | "manual";
  category: string;
  age_months: number;
  order_id?: string;
  /**
   * Demo-only deterministic id. The mock honours it so the graded item is the
   * same id threaded through the golden path; the live backend ignores it and
   * assigns its own id.
   */
  item_id?: string;
  original_price?: number;
  expected_price?: number;
}

/** Existing-backend item/grade/listing surface (BACKEND_MAP §5). */
export interface ItemsService {
  readonly mode: "mock" | "live";
  createItem(input: CreateItemInput): Promise<ItemMeta>;
  presignPhotos(itemId: string, count: number): Promise<PresignResponse>;
  enqueueGrade(itemId: string, photoKeys: string[]): Promise<GradeAccepted>;
  getItem(itemId: string): Promise<ItemAggregate>;
  route(itemId: string, geohash5?: string): Promise<RouteDecision>;
  createListing(input: {
    item_id: string;
    category: string;
    price: string;
    geohash5: string;
  }): Promise<unknown>;
  buy(itemId: string): Promise<BuyResponse>;
  verifyCard(cardId: string, sig: string): Promise<CardVerification>;
}

/** G1 — matching. */
export interface MatchingService {
  readonly mode: "mock" | "live";
  getMatches(itemId: string): Promise<MatchesResponse>;
}

/** G2 — review queue. */
export interface ReviewService {
  readonly mode: "mock" | "live";
  getQueue(): Promise<ReviewQueueResponse>;
  act(itemId: string, action: ReviewAction): Promise<ItemAggregate>;
}

/** G3/G4 — marketplace (extended item shape). */
export interface MarketplaceService {
  readonly mode: "mock" | "live";
  list(category: string): Promise<MarketplaceResponse>;
}

/**
 * Health Card — composed from the EXISTING public verify endpoint + the item
 * grade facet. Rides the items backend (no new gap endpoint); identified by
 * health_card_id or item_id.
 */
export interface HealthCardService {
  readonly mode: "mock" | "live";
  get(idOrCardId: string): Promise<HealthCardView>;
}
