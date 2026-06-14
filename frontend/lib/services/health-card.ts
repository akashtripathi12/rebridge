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
    const seed = seedHealthCard(idOrCardId);
    let cardId = seed?.card_id;
    let sig = seed?.signature;
    let itemId = seed?.item_id ?? idOrCardId;

    // We verify first (gets grade/warranty/signature/verified), then enrich
    // confidence + structured defects from the item.
    // For live items, we only have the item_id from the route.
    const item = await itemsService.getItem(itemId);
    
    if (!seed) {
        if (!item.card) {
            throw new Error(`Health card not found for item: ${itemId}`);
        }
        cardId = item.card.card_id;
        sig = item.card.signature;
    }

    const verify = await itemsService.verifyCard(cardId!, sig!);
    const grade = item.grade;
    let images: string[] = [];
    if (typeof window !== "undefined") {
      try {
        const stored = sessionStorage.getItem(`rb:photos:${itemId}`);
        if (stored) images = JSON.parse(stored);
      } catch (e) {
        // ignore
      }
    }
    if (images.length === 0) {
      images = item.card?.annotated_photo_keys ?? [];
    }

    return healthCardViewSchema.parse({
      card_id: cardId,
      item_id: itemId,
      title: seed?.title ?? `Resold Item (${itemId.slice(-6)})`,
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
      thumb_key: images[0] || seed?.thumb_key || "shoe",
      images: images,
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
