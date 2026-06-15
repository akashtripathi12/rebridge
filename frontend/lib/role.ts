"use client";

import { sessionStore, useSession, type Role } from "./session";

/**
 * Viewer role — Customer (default) or Operator. The role now comes from the
 * signed-in session (`custom:role`), not a free-floating toggle: it is set at
 * registration and recovered on login. `roleStore`/`useRole` are kept as the
 * stable read API the existing chrome uses, but they are thin views over the
 * session so role and identity can never drift apart.
 *
 * The in-nav switch (`roleStore.set`) remains for the demo only; in production
 * role changes happen in Cognito, not the client.
 */
export type { Role };

export const roleStore = {
  get(): Role {
    return sessionStore.get()?.role ?? "customer";
  },
  set(next: Role) {
    sessionStore.setRole(next);
  },
  toggle() {
    this.set(this.get() === "customer" ? "operator" : "customer");
  },
};

export function useRole(): Role {
  const session = useSession();
  return session?.role ?? "customer";
}
