"use client";

import { useSyncExternalStore } from "react";

export interface Notif {
  id: string;
  variant: "seller" | "buyer" | "system";
  title: string;
  body: string;
  meta?: string;
  href?: string;
  created_at: string;
  unread: boolean;
}

const KEY = "rb:notifs";

const SEEDS: Notif[] = [
  {
    id: "n_welcome",
    variant: "system",
    title: "Welcome to ReBridge",
    body: "Photograph a return, get a ₹3 AI grade, and route it to its next owner — or browse Second Chance to buy verified items nearby.",
    meta: "today",
    href: "/resell",
    created_at: new Date().toISOString(),
    unread: true,
  },
];

let state: Notif[] = SEEDS;
const listeners = new Set<() => void>();

function load(): Notif[] {
  if (typeof window === "undefined") return SEEDS;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : SEEDS;
  } catch {
    return SEEDS;
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

function set(next: Notif[]) {
  state = next;
  persist();
  listeners.forEach((l) => l());
}

export const notifs = {
  list(): Notif[] {
    ensureHydrated();
    return state;
  },
  add(n: Omit<Notif, "id" | "created_at" | "unread">) {
    ensureHydrated();
    const next: Notif = {
      ...n,
      id: `n_${Math.random().toString(36).slice(2, 10)}`,
      created_at: new Date().toISOString(),
      unread: true,
    };
    set([next, ...state]);
  },

  /**
   * Notify nearby buyers when a seller lists a product.
   * Uses actual match data to build the notification dynamically.
   */
  notifyBuyersOfNewListing(product: {
    title: string;
    grade: string;
    price: string;
    itemId: string;
    matchCount: number;
    topDistance?: number;
    topReason?: string | null;
  }) {
    ensureHydrated();
    const dist = product.topDistance ?? 5;
    const reason = product.topReason
      ? ` — ${product.topReason}`
      : "";
    const next: Notif = {
      id: `n_${Math.random().toString(36).slice(2, 10)}`,
      variant: "buyer",
      title: "A graded match near you",
      body: `${product.title} — ${product.grade}, ₹${product.price}, ${dist} km away.${reason}`,
      meta: "just now",
      href: `/product/${product.itemId}`,
      created_at: new Date().toISOString(),
      unread: true,
    };
    set([next, ...state]);
  },

  /**
   * Notify the seller when their listed product gets confirmed/graded
   * and matched to nearby buyers.
   */
  notifySellerOfRouting(product: {
    title: string;
    grade: string;
    price: string;
    matchCount: number;
  }) {
    ensureHydrated();
    const next: Notif = {
      id: `n_${Math.random().toString(36).slice(2, 10)}`,
      variant: "seller",
      title: `Routed to ${product.matchCount} buyer${product.matchCount !== 1 ? "s" : ""} < 5 km`,
      body: `${product.title} — ${product.grade}, listed for ₹${product.price}. AI matched ${product.matchCount} nearby buyer${product.matchCount !== 1 ? "s" : ""}.`,
      meta: "just now",
      href: "/resell/listings",
      created_at: new Date().toISOString(),
      unread: true,
    };
    set([next, ...state]);
  },

  /**
   * Notify the seller when a buyer shows interest (reserves) their product.
   */
  notifySellerOfInterest(product: {
    title: string;
    grade: string;
    price: string;
    buyerDistance: number;
    itemId: string;
  }) {
    ensureHydrated();
    const next: Notif = {
      id: `n_${Math.random().toString(36).slice(2, 10)}`,
      variant: "seller",
      title: "A buyer reserved your item",
      body: `${product.title} — ${product.grade}, ₹${product.price}. Buyer is ${product.buyerDistance} km away. Pickup scheduled.`,
      meta: "just now",
      href: "/resell/listings",
      created_at: new Date().toISOString(),
      unread: true,
    };
    set([next, ...state]);
  },

  markRead(id: string) {
    ensureHydrated();
    set(state.map((n) => (n.id === id ? { ...n, unread: false } : n)));
  },
  markAllRead() {
    ensureHydrated();
    set(state.map((n) => ({ ...n, unread: false })));
  },
  unreadCount(): number {
    ensureHydrated();
    return state.filter((n) => n.unread).length;
  },
};

export function useNotifs(): Notif[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
    () => SEEDS,
  );
}
