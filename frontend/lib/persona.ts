/**
 * Demo persona seed. "Rahul" makes the buyer narrative one deterministic click:
 * a routed match → marketplace → listing → Health Card → reserve. The routed
 * item is fixed so the demo is identical every run.
 */
export const RAHUL = {
  id: "buyer-rahul",
  name: "Rahul",
  city: "BLR",
  intentCategory: "shoes",
  /** The item the matching engine routed to Rahul (highlighted in the push). */
  routedItemId: "itm_shoe7",
} as const;
