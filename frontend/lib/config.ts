/**
 * Runtime config + the per-service mock→live flags.
 *
 * Each gap endpoint (G1 matching, G2 review, G3/G4 marketplace) has ONE env
 * flag. Default false (mock). Flipping a flag to "true" is the one-line change
 * that swaps a mock service for its live implementation — the UI never knows
 * which it got. See FOR_BACKEND.md for the flip-to-go-live table.
 */

export const config = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
    "http://localhost:8000",

  // Gap-service live switches (G1/G2/G3). Default mock.
  matchingLive: process.env.NEXT_PUBLIC_MATCHING_LIVE === "true",
  reviewLive: process.env.NEXT_PUBLIC_REVIEW_LIVE === "true",
  marketplaceLive: process.env.NEXT_PUBLIC_MARKETPLACE_LIVE === "true",

  // The existing-backend endpoints (items/grade/cards) also have a switch so
  // Phase 2/3 can run fully offline against the in-memory mock until the worker
  // is up. Default mock for autonomous-night build; flip when the backend runs.
  itemsLive: process.env.NEXT_PUBLIC_ITEMS_LIVE === "true",

  // Cognito (G8) — public values, safe in the client. Real values wired last.
  cognito: {
    region: process.env.NEXT_PUBLIC_COGNITO_REGION || "us-east-1",
    userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID || "",
    appClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID || "",
  },
} as const;

/** Grade label union — verbatim from the backend Grade enum. */
export const GRADES = [
  "Like New",
  "Very Good",
  "Good",
  "Acceptable",
  "Unsellable",
] as const;
export type GradeLabel = (typeof GRADES)[number];

/** Disposition union — verbatim from the backend Disposition enum. */
export const DISPOSITIONS = ["RESELL", "REFURB", "P2P", "DONATE"] as const;
export type DispositionLabel = (typeof DISPOSITIONS)[number];

/** Item lifecycle status — verbatim from ItemStatus. */
export const ITEM_STATUSES = [
  "CREATED",
  "RETAKE_REQUIRED",
  "GRADING",
  "PENDING_REVIEW",
  "GRADED",
  "LISTED",
  "SOLD",
] as const;
export type ItemStatusLabel = (typeof ITEM_STATUSES)[number];

/** Terminal poll states for async grading (G6). */
export const GRADING_TERMINAL: ItemStatusLabel[] = [
  "GRADED",
  "PENDING_REVIEW",
  "RETAKE_REQUIRED",
];
