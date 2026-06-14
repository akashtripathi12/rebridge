import { healthCardViewSchema, type HealthCardView } from "../schemas";
import { config } from "../config";
import { seedHealthCard } from "../seed";
import { itemsService } from "./items";
import type { HealthCardService } from "./types";

/**
 * The Health Card is composed from EXISTING backend responses (no gap endpoint):
 *   GET /cards/{card_id}/verify  → verified + grade + warranty + signature + qr
 *   GET /items/{item_id}         → confidence + structured defects
 * It therefore rides the items backend flag (NEXT_PUBLIC_ITEMS_LIVE). Mock builds
 * the same view from seed.
 */
class LiveHealthCardService implements HealthCardService {
  readonly mode = "live" as const;
  async get(idOrCardId: string): Promise<HealthCardView> {
    // For the live path the caller passes a card_id; verify is public + needs
    // the signature, which is embedded in the seeded qr_target / card facet.
    // We verify first (gets grade/warranty/signature/verified), then enrich
    // confidence + structured defects from the item.
    const seed = seedHealthCard(idOrCardId);
    const cardId = seed?.card_id ?? idOrCardId;
    const sig = seed?.signature ?? "";
    const verify = await itemsService.verifyCard(cardId, sig);
    const itemId = verify.card?.item_id ?? seed?.item_id ?? idOrCardId;
    const item = await itemsService.getItem(itemId);
    const grade = item.grade;
    return healthCardViewSchema.parse({
      card_id: cardId,
      item_id: itemId,
      title: seed?.title ?? itemId,
      grade: grade?.grade ?? verify.card?.grade ?? "Good",
      confidence: grade?.confidence ?? 0,
      defects: grade?.defects ?? [],
      warranty_stance: verify.card?.warranty_stance ?? "",
      graded_at: verify.card?.graded_at ?? "",
      signature: verify.card?.signature ?? sig,
      qr_target: verify.card?.qr_target ?? `/cards/${cardId}/verify?sig=${sig}`,
      verified: verify.verified,
      price: item.decision?.price ?? seed?.price ?? "0",
      price_new: item.decision?.price_new ?? seed?.price_new ?? "0",
      thumb_key: seed?.thumb_key ?? "shoe",
    });
  }
}

class MockHealthCardService implements HealthCardService {
  readonly mode = "mock" as const;
  async get(idOrCardId: string): Promise<HealthCardView> {
    const view = seedHealthCard(idOrCardId);
    if (!view) throw new Error(`health card not found: ${idOrCardId}`);
    return healthCardViewSchema.parse(view);
  }
}

export const healthCardService: HealthCardService = config.itemsLive
  ? new LiveHealthCardService()
  : new MockHealthCardService();
