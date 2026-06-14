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
    id: "n_match_shoe",
    variant: "buyer",
    title: "A graded match near you",
    body: "Running Shoes · UK 7 — GOOD, ₹340, 4 km. Wishlisted these.",
    meta: "just now",
    href: "/product/itm_shoe7",
    created_at: new Date().toISOString(),
    unread: true,
  },
  {
    id: "n_listing_sample",
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
