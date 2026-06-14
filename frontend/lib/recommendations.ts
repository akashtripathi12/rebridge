/**
 * Client-side recommendation engine.
 *
 * Scores existing marketplace listings against a buyer persona to produce
 * personalized, sectioned recommendations. No backend calls — runs entirely
 * in the browser on the already-fetched marketplace data.
 */

import type { MarketplaceItem } from "./schemas";
import { percentSaved } from "./format";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BuyerProfile {
  intentCategory: string;
  secondaryInterests: readonly string[];
  priceProfile: "deal_seeker" | "price_balker" | "browser" | "collector" | "gifter";
}

export interface ScoredItem extends MarketplaceItem {
  /** Overall relevance score 0–1, combining all signals. */
  relevanceScore: number;
  /** Human-readable reason this item was recommended. */
  recommendationReason: string;
  /** Discount percentage (null if not calculable). */
  discountPct: number | null;
}

export interface RecommendationSections {
  /** Top items by overall relevance score. */
  forYou: ScoredItem[];
  /** Items with ≥ 30 % discount, sorted by discount desc. */
  topDeals: ScoredItem[];
  /** Items within 5 km, sorted by distance asc. */
  nearYou: ScoredItem[];
}

// ---------------------------------------------------------------------------
// Scoring weights
// ---------------------------------------------------------------------------

const W_CATEGORY = 0.35;
const W_PRICE = 0.25;
const W_GEO = 0.20;
const W_GRADE = 0.20;

// ---------------------------------------------------------------------------
// Grade quality mapping
// ---------------------------------------------------------------------------

const GRADE_SCORE: Record<string, number> = {
  "Like New": 1.0,
  "Very Good": 0.8,
  "Good": 0.6,
  "Acceptable": 0.4,
  "Unsellable": 0.0,
};

// ---------------------------------------------------------------------------
// Signal computations
// ---------------------------------------------------------------------------

function categorySignal(
  itemCategory: string,
  buyer: BuyerProfile,
): { score: number; reason: string | null } {
  const cat = itemCategory.toLowerCase();
  if (cat === buyer.intentCategory.toLowerCase()) {
    return { score: 1.0, reason: `Matches your interest in ${itemCategory}` };
  }
  if (buyer.secondaryInterests.some((s) => s.toLowerCase() === cat)) {
    return { score: 0.45, reason: `Related to your ${itemCategory} interests` };
  }
  return { score: 0.05, reason: null };
}

function priceSignal(
  price: string,
  priceNew: string,
  buyer: BuyerProfile,
): { score: number; discountPct: number | null; reason: string | null } {
  const pct = percentSaved(price, priceNew);
  if (pct == null) return { score: 0.3, discountPct: null, reason: null };

  // Deal-seekers and price-balkers value discounts more
  const sensitivity =
    buyer.priceProfile === "deal_seeker" || buyer.priceProfile === "price_balker"
      ? 1.2
      : 1.0;
  const raw = Math.min((pct / 100) * sensitivity, 1.0);
  const reason = pct >= 30 ? `${pct}% off retail price` : null;
  return { score: raw, discountPct: pct, reason };
}

function geoSignal(
  distanceKm: number,
  maxDistanceKm: number,
): { score: number; reason: string | null } {
  if (maxDistanceKm <= 0) return { score: 1.0, reason: null };
  const raw = Math.max(0, 1 - distanceKm / maxDistanceKm);
  const reason = distanceKm <= 2 ? `Just ${Math.round(distanceKm)} km away` : null;
  return { score: raw, reason };
}

function gradeSignal(grade: string | null | undefined): {
  score: number;
  reason: string | null;
} {
  if (!grade) return { score: 0.5, reason: null };
  const s = GRADE_SCORE[grade] ?? 0.5;
  const reason = grade === "Like New" ? "Like New condition" : null;
  return { score: s, reason };
}

// ---------------------------------------------------------------------------
// Pick the best reason
// ---------------------------------------------------------------------------

function pickBestReason(
  reasons: (string | null)[],
  fallback: string,
): string {
  // First non-null wins (ordered by signal strength)
  for (const r of reasons) {
    if (r) return r;
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Score a list of marketplace listings for a given buyer profile.
 * Returns all items with their relevance scores, sorted desc.
 */
export function scoreForBuyer(
  listings: MarketplaceItem[],
  buyer: BuyerProfile,
): ScoredItem[] {
  if (listings.length === 0) return [];

  // Compute max distance for normalization
  const maxDist = Math.max(...listings.map((l) => l.distance_km), 10);

  const scored: ScoredItem[] = listings.map((item) => {
    const cat = categorySignal(item.category, buyer);
    const price = priceSignal(item.price, item.price_new, buyer);
    const geo = geoSignal(item.distance_km, maxDist);
    const grade = gradeSignal(item.grade);

    const relevanceScore = Math.round(
      (W_CATEGORY * cat.score +
        W_PRICE * price.score +
        W_GEO * geo.score +
        W_GRADE * grade.score) *
        100,
    ) / 100;

    const recommendationReason = pickBestReason(
      [cat.reason, price.reason, geo.reason, grade.reason],
      "Verified second-life product",
    );

    return {
      ...item,
      relevanceScore,
      recommendationReason,
      discountPct: price.discountPct,
    };
  });

  scored.sort((a, b) => b.relevanceScore - a.relevanceScore);
  return scored;
}

/**
 * Build the recommendation sections from scored listings.
 */
export function buildSections(
  scored: ScoredItem[],
  options?: {
    forYouCount?: number;
    dealThreshold?: number;
    nearbyRadiusKm?: number;
  },
): RecommendationSections {
  const forYouCount = options?.forYouCount ?? 6;
  const dealThreshold = options?.dealThreshold ?? 30;
  const nearbyRadius = options?.nearbyRadiusKm ?? 5;

  const forYou = scored.slice(0, forYouCount);

  const topDeals = scored
    .filter((s) => s.discountPct != null && s.discountPct >= dealThreshold)
    .sort((a, b) => (b.discountPct ?? 0) - (a.discountPct ?? 0));

  const nearYou = scored
    .filter((s) => s.distance_km <= nearbyRadius)
    .sort((a, b) => a.distance_km - b.distance_km);

  return { forYou, topDeals, nearYou };
}
