/**
 * G8 — authProvider interface. Now: a session-backed mock so the demo runs with
 * no Cognito pool. Later: a Cognito-backed provider (Hosted UI / Amplify) swapped
 * in here with no call-site changes. The rest of the app only calls getToken().
 *
 * The token comes from the signed-in session (`lib/session.ts`) and carries the
 * `custom:role` claim, so the backend can enforce role on every request.
 */

import { sessionStore } from "./session";

export interface AuthProvider {
  getToken(): Promise<string | null>;
  readonly kind: "mock" | "cognito";
}

/** Dev provider — returns the current session's bearer (null when signed out). */
class MockAuthProvider implements AuthProvider {
  readonly kind = "mock" as const;
  async getToken(): Promise<string | null> {
    return sessionStore.get()?.token ?? null;
  }
}

// Cognito provider is wired last (G8). Stub kept here so the swap is one line:
// register → signUp({ username, password, attributes: { "custom:role": role } });
// login → initiateAuth(...); getToken → currentSession().getIdToken().getJwtToken().
// class CognitoAuthProvider implements AuthProvider { ... }

export const authProvider: AuthProvider = new MockAuthProvider();


