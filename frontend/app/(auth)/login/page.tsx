"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { sessionStore, UnknownAccountError } from "@/lib/session";
import { landingFor } from "@/components/chrome/role-route-guard";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      // Demo: role is recovered from the local directory. Production swap (see
      // lib/auth.ts): Cognito initiateAuth; role arrives in the verified id-token.
      const session = sessionStore.login(email.trim());
      const next = params.get("next");
      router.replace(next || landingFor(session.role));
    } catch (err) {
      if (err instanceof UnknownAccountError) {
        setError("No account found for that email. Create one first.");
      } else {
        setError("Could not sign in. Please try again.");
      }
    }
  }

  return (
    <main className="bg-canvas px-4 py-16 sm:px-6">
      <div className="mx-auto max-w-[460px]">
        <div className="rounded-card border border-hair bg-paper p-8 shadow-sm sm:p-10">
          <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
            Welcome back
          </div>
          <h1 className="mt-1 font-display text-[clamp(24px,3.5vw,30px)] font-extrabold uppercase leading-tight tracking-tight">
            Sign in
          </h1>

          <form className="mt-7 flex flex-col gap-5" onSubmit={onSubmit}>
            <label htmlFor="email" className="block">
              <span className="mb-2 block font-sans text-[12px] font-bold uppercase tracking-wider text-mute">
                Email
              </span>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email"
                className="w-full rounded-card border border-hair bg-white px-3.5 py-3 font-sans text-[14px] outline-none focus:border-ink"
                placeholder="you@example.com"
              />
            </label>

            <label htmlFor="password" className="block">
              <span className="mb-2 block font-sans text-[12px] font-bold uppercase tracking-wider text-mute">
                Password
              </span>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password"
                className="w-full rounded-card border border-hair bg-white px-3.5 py-3 font-sans text-[14px] outline-none focus:border-ink"
                placeholder="••••••••"
              />
            </label>

            {error ? (
              <p data-testid="login-error" className="text-[13px] font-semibold text-red-600">
                {error}
              </p>
            ) : null}

            <Button type="submit" variant="primary" size="block" data-testid="login-submit">
              Sign in
            </Button>
          </form>

          <p className="mt-5 text-center text-[13px] text-ash">
            New to ReBridge?{" "}
            <Link href="/register" className="font-semibold text-ink underline">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
