/**
 * G8 — authProvider interface. Now: a dev mock token so every phase proceeds
 * unblocked. Later: a Cognito-backed provider (Hosted UI / Amplify) swapped in
 * here with no call-site changes. The rest of the app only calls getToken().
 */

export interface AuthProvider {
  getToken(): Promise<string | null>;
  readonly kind: "mock" | "cognito";
}

/** Dev provider — returns a static fake bearer so private routes are callable. */
class MockAuthProvider implements AuthProvider {
  readonly kind = "mock" as const;
  async getToken(): Promise<string | null> {
    return "dev-mock-token";
  }
}

// Cognito provider is wired last (G8). Stub kept here so the swap is one line.
// class CognitoAuthProvider implements AuthProvider { ... }

export const authProvider: AuthProvider = new MockAuthProvider();
