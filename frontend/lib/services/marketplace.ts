import { marketplaceResponseSchema } from "../schemas";
import { apiFetch } from "../api";
import { config } from "../config";
import { SEED_MARKETPLACE } from "../seed";
import type { MarketplaceService } from "./types";

// G3/G4 — GET /marketplace extended with grade/distance/price_new (backend to
// extend). G9: a category is ALWAYS sent. "all" maps to a default until the
// backend confirms it accepts category=all (open question in FOR_BACKEND.md).
class LiveMarketplaceService implements MarketplaceService {
  readonly mode = "live" as const;
  list(category: string) {
    return apiFetch(`/marketplace`, {
      query: { category },
      schema: marketplaceResponseSchema,
    });
  }
}

class MockMarketplaceService implements MarketplaceService {
  readonly mode = "mock" as const;
  async list(category: string) {
    const all = SEED_MARKETPLACE;
    const listings =
      category === "all" || !category
        ? all
        : all.filter((m) => m.category === category);
    return marketplaceResponseSchema.parse({ listings });
  }
}

export const marketplaceService: MarketplaceService = config.marketplaceLive
  ? new LiveMarketplaceService()
  : new MockMarketplaceService();
