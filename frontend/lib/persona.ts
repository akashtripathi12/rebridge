/**
 * Demo persona seed. "Rahul" makes the buyer narrative one deterministic click:
 * a routed match → marketplace → listing → Health Card → reserve. The routed
 * item is fixed so the demo is identical every run.
 *
 * `secondaryInterests` and `priceProfile` feed the client-side recommendation
 * engine so the marketplace page surfaces personalized sections.
 */
export const RAHUL = {
  id: "buyer-rahul",
  name: "Rahul",
  city: "BLR",
  intentCategory: "shoes",
  /** Secondary browsing interests for recommendation scoring. */
  secondaryInterests: ["tech", "books"] as readonly string[],
  /** Persona type used to weight price-sensitivity in scoring. */
  priceProfile: "deal_seeker" as const,
  /** The item the matching engine routed to Rahul (highlighted in the push). */
  routedItemId: "itm_shoe7",
} as const;
