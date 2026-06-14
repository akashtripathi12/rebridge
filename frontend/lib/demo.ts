"use client";

import { useSyncExternalStore } from "react";

/**
 * The golden-path spine. ONE seeded demo item travels capture → grade → route →
 * buyer → reserved, threaded by a single id through every screen. The id is the
 * already-seeded hero item (marketplace top match + health card + matches all
 * resolve for it), so "the item I graded" IS "the item in the marketplace".
 */
export const DEMO_ITEM_ID = "itm_shoe7";

export const DEMO_ITEM = {
  item_id: DEMO_ITEM_ID,
  title: "Running Shoes · UK 7",
  category: "shoes",
  order_id: "AMZ-7F3A",
  age_months: 8,
  price: "340.00",
} as const;

/** The five story beats shown on the progress rail. */
export const BEATS = ["capture", "grade", "route", "buyer", "reserved"] as const;
export type Beat = (typeof BEATS)[number];
export const BEAT_LABELS: Record<Beat, string> = {
  capture: "Capture",
  grade: "Grade",
  route: "Route",
  buyer: "Buyer",
  reserved: "Reserved",
};

interface JourneyState {
  itemId: string | null;
  beat: Beat;
  listed: boolean;
  reserved: boolean;
}

const KEY = "rb:journey";
const empty: JourneyState = {
  itemId: null,
  beat: "capture",
  listed: false,
  reserved: false,
};

let state: JourneyState = empty;
const listeners = new Set<() => void>();

function load(): JourneyState {
  if (typeof window === "undefined") return empty;
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? { ...empty, ...JSON.parse(raw) } : empty;
  } catch {
    return empty;
  }
}

function persist() {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

function set(patch: Partial<JourneyState>) {
  state = { ...state, ...patch };
  persist();
  listeners.forEach((l) => l());
}

// Hydrate from sessionStorage once on the client.
let hydrated = false;
function ensureHydrated() {
  if (!hydrated && typeof window !== "undefined") {
    state = load();
    hydrated = true;
  }
}

export const journey = {
  start(itemId: string) {
    ensureHydrated();
    set({ itemId, beat: "grade", listed: false, reserved: false });
  },
  setBeat(beat: Beat) {
    ensureHydrated();
    if (state.beat !== beat) set({ beat });
  },
  markListed() {
    ensureHydrated();
    set({ listed: true, beat: "route" });
  },
  markReserved() {
    ensureHydrated();
    set({ reserved: true, beat: "reserved" });
  },
  reset() {
    set({ ...empty });
  },
  get(): JourneyState {
    ensureHydrated();
    return state;
  },
};

/** Subscribe to the journey store from React. */
export function useJourney(): JourneyState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
    () => empty,
  );
}
