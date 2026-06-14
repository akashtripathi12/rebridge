"use client";

import { useSyncExternalStore } from "react";

/**
 * Viewer role — Customer (default) or Operator. Persisted in localStorage. In
 * production this will come from auth; today it's a manual switcher in the nav,
 * which is exactly what the brief asks for ("a button to switch between operator
 * and customer; later we will show the site based on auth").
 */
export type Role = "customer" | "operator";

const KEY = "rb:role";
let role: Role = "customer";
const listeners = new Set<() => void>();

function load(): Role {
  if (typeof window === "undefined") return "customer";
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw === "operator" ? "operator" : "customer";
  } catch {
    return "customer";
  }
}

let hydrated = false;
function ensureHydrated() {
  if (!hydrated && typeof window !== "undefined") {
    role = load();
    hydrated = true;
  }
}

export const roleStore = {
  get(): Role {
    ensureHydrated();
    return role;
  },
  set(next: Role) {
    ensureHydrated();
    if (role === next) return;
    role = next;
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l());
  },
  toggle() {
    this.set(role === "customer" ? "operator" : "customer");
  },
};

export function useRole(): Role {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => role,
    () => "customer",
  );
}
