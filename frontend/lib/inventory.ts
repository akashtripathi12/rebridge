"use client";

import { useSyncExternalStore } from "react";

/**
 * Local inventory: things the current user has either LISTED (resold) or
 * PURCHASED (bought from Second Chance). Persisted in localStorage so a user
 * can list one item, navigate away, come back to /resell/listings and still see
 * it — which is what "a real product, not a demo" requires.
 *
 * In live mode the source of truth would be the backend's per-user views; this
 * client store is the same shape so swapping it for a service call is local.
 */

export interface MyListing {
  item_id: string;
  title: string;
  category: string;
  grade: string;
  confidence: number;
  price: string; // money string
  price_new?: string;
  thumb_key: string;
  health_card_id: string;
  status: "LISTED" | "RESERVED" | "SOLD";
  listed_at: string;
  green_credits?: number;
}

export interface MyPurchase {
  item_id: string;
  title: string;
  grade: string;
  price: string;
  thumb_key: string;
  health_card_id: string;
  status: "RESERVED" | "PAID" | "DELIVERED";
  reserved_at: string;
  pickup_at: string;
}

interface InventoryState {
  listings: MyListing[];
  purchases: MyPurchase[];
}

const KEY = "rb:inventory";
const empty: InventoryState = { listings: [], purchases: [] };
let state: InventoryState = empty;
const listeners = new Set<() => void>();

function load(): InventoryState {
  if (typeof window === "undefined") return empty;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return empty;
    const parsed = JSON.parse(raw);
    return {
      listings: Array.isArray(parsed.listings) ? parsed.listings : [],
      purchases: Array.isArray(parsed.purchases) ? parsed.purchases : [],
    };
  } catch {
    return empty;
  }
}

function persist() {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

let hydrated = false;
function ensureHydrated() {
  if (!hydrated && typeof window !== "undefined") {
    state = load();
    hydrated = true;
  }
}

function set(next: InventoryState) {
  state = next;
  persist();
  listeners.forEach((l) => l());
}

export const inventory = {
  get(): InventoryState {
    ensureHydrated();
    return state;
  },
  addListing(listing: MyListing) {
    ensureHydrated();
    const without = state.listings.filter((l) => l.item_id !== listing.item_id);
    set({ ...state, listings: [listing, ...without] });
  },
  updateListingStatus(itemId: string, status: MyListing["status"]) {
    ensureHydrated();
    set({
      ...state,
      listings: state.listings.map((l) =>
        l.item_id === itemId ? { ...l, status } : l,
      ),
    });
  },
  addPurchase(purchase: MyPurchase) {
    ensureHydrated();
    const without = state.purchases.filter((p) => p.item_id !== purchase.item_id);
    set({ ...state, purchases: [purchase, ...without] });
  },
  reset() {
    set(empty);
  },
};

export function useInventory(): InventoryState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => {
      ensureHydrated();
      return state;
    },
    () => empty,
  );
}
