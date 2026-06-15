"use client";

import { useSyncExternalStore } from "react";

/**
 * Auth session — the single source of truth for *who* is signed in and *what
 * role* they hold. Role drives both the API bearer (the backend re-checks
 * `custom:role` on every operator route) and the frontend route guards.
 *
 * Today this is a localStorage-backed mock so the demo runs with no Cognito
 * pool. The shape is deliberately the same one a Cognito id-token gives us, so
 * going live is a contained swap (see `lib/auth.ts`):
 *   - register()  → Cognito `signUp` with a `custom:role` user attribute
 *   - login()     → Cognito `initiateAuth`; role read from the verified id-token
 *   - token       → the real id-token (this mock mints an unsigned look-alike)
 *
 * The role is carried inside the token as the `custom:role` claim, exactly like
 * Cognito, so `apiFetch` sends it and the server enforces it regardless of the
 * client. The frontend NEVER trusts role for anything security-sensitive — the
 * guards here are UX only; the real gate is the backend `RequireOperator`.
 */

export type Role = "operator" | "customer";

export interface Session {
  email: string;
  role: Role;
  /** Bearer sent on live API calls. Mock: an unsigned JWT carrying custom:role. */
  token: string;
}

const SESSION_KEY = "rb:session";
// Demo-only directory so login() can recover the role a user registered with.
// In production the role lives in Cognito and arrives inside the id-token; this
// map does not exist there.
const USERS_KEY = "rb:users";

const listeners = new Set<() => void>();
let current: Session | null = null;
let hydrated = false;

function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Session>;
    if (
      parsed &&
      (parsed.role === "operator" || parsed.role === "customer") &&
      typeof parsed.token === "string" &&
      typeof parsed.email === "string"
    ) {
      return { email: parsed.email, role: parsed.role, token: parsed.token };
    }
  } catch {
    /* ignore corrupt session */
  }
  return null;
}

function ensureHydrated() {
  if (!hydrated && typeof window !== "undefined") {
    current = readSession();
    hydrated = true;
  }
}

function persist(next: Session | null) {
  current = next;
  try {
    if (next) window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore quota / privacy-mode errors */
  }
  listeners.forEach((l) => l());
}

function readUsers(): Record<string, Role> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(USERS_KEY) || "{}");
  } catch {
    return {};
  }
}

function rememberUser(email: string, role: Role) {
  try {
    const users = readUsers();
    users[email.toLowerCase()] = role;
    window.localStorage.setItem(USERS_KEY, JSON.stringify(users));
  } catch {
    /* ignore */
  }
}

function base64url(value: string): string {
  const b64 =
    typeof window === "undefined"
      ? Buffer.from(value, "utf-8").toString("base64")
      : window.btoa(unescape(encodeURIComponent(value)));
  return b64.replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

/**
 * Mint an unsigned JWT look-alike carrying `custom:role`. The mock backend
 * override ignores the signature; a real deployment replaces this with the
 * Cognito id-token, which the backend verifies. The claim name matches Cognito
 * exactly so no call site changes when we swap providers.
 */
function mintMockToken(email: string, role: Role): string {
  const header = base64url(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = base64url(
    JSON.stringify({ sub: email, email, "custom:role": role }),
  );
  return `${header}.${payload}.mock`;
}

export class UnknownAccountError extends Error {
  constructor(email: string) {
    super(`No account found for ${email}. Please register first.`);
    this.name = "UnknownAccountError";
  }
}

export const sessionStore = {
  get(): Session | null {
    ensureHydrated();
    return current;
  },

  /** Create an account with the chosen role and sign in (demo: mock-only). */
  register(email: string, role: Role): Session {
    ensureHydrated();
    rememberUser(email, role);
    const session: Session = { email, role, token: mintMockToken(email, role) };
    persist(session);
    return session;
  },

  /** Sign in an existing account; role is recovered from the demo directory. */
  login(email: string): Session {
    ensureHydrated();
    const role = readUsers()[email.toLowerCase()];
    if (!role) throw new UnknownAccountError(email);
    const session: Session = { email, role, token: mintMockToken(email, role) };
    persist(session);
    return session;
  },

  logout() {
    ensureHydrated();
    persist(null);
  },

  /**
   * Demo convenience for the in-nav role switch: flip the current session's
   * role (creating a throwaway demo session if signed out). Not a production
   * affordance — role changes go through Cognito there.
   */
  setRole(role: Role) {
    ensureHydrated();
    const email = current?.email ?? "demo@rebridge.dev";
    persist({ email, role, token: mintMockToken(email, role) });
  },
};

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Reactive hook returning the current session (null when signed out). */
export function useSession(): Session | null {
  return useSyncExternalStore(
    subscribe,
    () => {
      ensureHydrated();
      return current;
    },
    () => null,
  );
}
