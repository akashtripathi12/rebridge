/**
 * G9 assumption: `GET /marketplace?category=all` is accepted by the backend.
 * Routed through ONE constant so that if the backend rejects "all", omitting the
 * param (or substituting a default category) is a one-line change. Documented in
 * FOR_BACKEND.md.
 */
export const MARKETPLACE_ALL_CATEGORY = "all";

/** Buyer-facing category chips. "Nearby" maps to the all-category constant. */
export const MARKET_CATEGORIES: { id: string; label: string }[] = [
  { id: MARKETPLACE_ALL_CATEGORY, label: "Nearby" },
  { id: "baby", label: "Baby & kids" },
  { id: "shoes", label: "Shoes" },
  { id: "tech", label: "Tech" },
  { id: "books", label: "Books" },
];
