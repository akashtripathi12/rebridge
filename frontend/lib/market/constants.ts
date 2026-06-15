/**
 * G9 assumption: `GET /marketplace?category=all` is accepted by the backend.
 * Routed through ONE constant so that if the backend rejects "all", omitting the
 * param (or substituting a default category) is a one-line change. Documented in
 * FOR_BACKEND.md.
 */
export const MARKETPLACE_ALL_CATEGORY = "all";

/** Buyer-facing category chips. "For you" triggers recommendation sections. */
export const MARKET_CATEGORIES: { id: string; label: string }[] = [
  { id: "for_you", label: "For you ✨" },
  { id: MARKETPLACE_ALL_CATEGORY, label: "All" },
  { id: "baby", label: "Baby & kids" },
  { id: "shoes", label: "Shoes" },
  { id: "tech", label: "Tech" },
  { id: "books", label: "Books" },
];
