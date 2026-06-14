import { matchesResponseSchema } from "../schemas";
import { apiFetch } from "../api";
import { config } from "../config";
import { seedMatches } from "../seed";
import type { MatchingService } from "./types";

// G1 — GET /items/{id}/matches (backend to add, per addendum).
class LiveMatchingService implements MatchingService {
  readonly mode = "live" as const;
  getMatches(itemId: string) {
    return apiFetch(`/items/${itemId}/matches`, {
      schema: matchesResponseSchema,
    });
  }
}

class MockMatchingService implements MatchingService {
  readonly mode = "mock" as const;
  async getMatches(itemId: string) {
    return matchesResponseSchema.parse(seedMatches(itemId));
  }
}

export const matchingService: MatchingService = config.matchingLive
  ? new LiveMatchingService()
  : new MockMatchingService();
