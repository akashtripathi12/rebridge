"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSession, type Role } from "@/lib/session";

/**
 * Layout-level guard for a role-scoped route group. Reads the session role and:
 *   - signed out          → /login (remembering where they were headed)
 *   - signed in, wrong role → that role's own landing (cross-role redirect)
 *   - signed in, right role → renders the protected subtree
 *
 * This is UX only — it keeps the wrong audience from seeing a screen. The real
 * authorization is the backend `RequireOperator` gate, which re-checks
 * `custom:role` on every request no matter what the client renders.
 */
export function RoleRouteGuard({
  allow,
  children,
}: {
  allow: Role;
  children: React.ReactNode;
}) {
  const session = useSession();
  const pathname = usePathname() ?? "/";
  const router = useRouter();

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    if (session === null) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (session.role !== allow) {
      router.replace(landingFor(session.role));
    }
  }, [session, allow, pathname, router, mounted]);

  if (!mounted || !session || session.role !== allow) {
    return (
      <div
        data-testid="route-guard-pending"
        className="grid min-h-[60vh] place-items-center px-6 text-[13px] text-mute"
      >
        Checking access…
      </div>
    );
  }

  return <>{children}</>;
}

/**
 * The landing screen for a given role — used for post-login and cross-role
 * redirects. Customers land on the public home page; operators have no home
 * page and go straight to their review console.
 */
export function landingFor(role: Role): string {
  return role === "operator" ? "/operator/review-queue" : "/";
}
