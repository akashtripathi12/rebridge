"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ShoppingBag, UserCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { config } from "@/lib/config";
import { sessionStore, type Role } from "@/lib/session";
import { landingFor } from "@/components/chrome/role-route-guard";
import { cn } from "@/lib/utils";

function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("customer");

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    // Demo: mint a session locally. Production swap (see lib/auth.ts): Cognito
    // signUp with a `custom:role` attribute, then sign in.
    sessionStore.register(email.trim(), role);
    const next = params.get("next");
    router.replace(next || landingFor(role));
  }

  return (
    <main className="bg-canvas px-4 py-16 sm:px-6">
      <div className="mx-auto max-w-[460px]">
        <div className="rounded-card border border-hair bg-paper p-8 shadow-sm sm:p-10">
          <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
            Create account
          </div>
          <h1 className="mt-1 font-display text-[clamp(24px,3.5vw,30px)] font-extrabold uppercase leading-tight tracking-tight">
            Join ReBridge
          </h1>

          <form className="mt-7 flex flex-col gap-5" onSubmit={onSubmit}>
            <Field label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="register-email"
                className="w-full rounded-card border border-hair bg-white px-3.5 py-3 font-sans text-[14px] outline-none focus:border-ink"
                placeholder="you@example.com"
              />
            </Field>

            <Field label="Password" htmlFor="password">
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="register-password"
                className="w-full rounded-card border border-hair bg-white px-3.5 py-3 font-sans text-[14px] outline-none focus:border-ink"
                placeholder="••••••••"
              />
            </Field>

            <div>
              <div className="mb-2 font-sans text-[12px] font-bold uppercase tracking-wider text-mute">
                I am a…
              </div>
              <div
                data-testid="register-role"
                data-role={role}
                className="grid grid-cols-2 gap-2"
              >
                <RoleOption
                  active={role === "customer"}
                  onClick={() => setRole("customer")}
                  Icon={ShoppingBag}
                  title="Customer"
                  sub="Browse & buy second-life products"
                  testid="role-pick-customer"
                />
                {config.allowOperatorSignup ? (
                  <RoleOption
                    active={role === "operator"}
                    onClick={() => setRole("operator")}
                    Icon={UserCog}
                    title="Operator"
                    sub="Grade returns & run the review console"
                    testid="role-pick-operator"
                  />
                ) : (
                  <div className="rounded-card border border-dashed border-hair bg-canvas px-3 py-3 text-[12px] leading-snug text-mute">
                    Operator accounts are <b>invite-only</b>. Contact your admin
                    to be provisioned.
                  </div>
                )}
              </div>
            </div>

            <Button type="submit" variant="primary" size="block" data-testid="register-submit">
              Create account
            </Button>
          </form>

          <p className="mt-5 text-center text-[13px] text-ash">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-ink underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="block">
      <span className="mb-2 block font-sans text-[12px] font-bold uppercase tracking-wider text-mute">
        {label}
      </span>
      {children}
    </label>
  );
}

function RoleOption({
  active,
  onClick,
  Icon,
  title,
  sub,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  sub: string;
  testid: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      data-active={active}
      className={cn(
        "flex flex-col items-start gap-1 rounded-card border px-3 py-3 text-left transition-colors",
        active ? "border-ink bg-white shadow-sm" : "border-hair bg-canvas hover:border-ink/30",
      )}
    >
      <Icon className="h-4 w-4 text-ink" />
      <span className="font-sans text-[13px] font-bold text-ink">{title}</span>
      <span className="text-[11px] leading-snug text-mute">{sub}</span>
    </button>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}
