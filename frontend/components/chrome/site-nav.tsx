"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell, LogOut, Menu, Repeat, RotateCcw, ShieldCheck, ShoppingBag, Tag, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRole } from "@/lib/role";
import { useSession, sessionStore } from "@/lib/session";
import { useNotifs } from "@/lib/notifications";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
}

// Customers only ever see buyer/seller surfaces; operators only ever see the
// back office. The route-group guards enforce this server-of-truth split; this
// nav simply reflects it so each role sees only its own destinations.
const CUSTOMER_NAV: NavItem[] = [
  { href: "/marketplace", label: "Market", Icon: ShoppingBag },
  { href: "/resell", label: "Resell", Icon: Repeat },
  { href: "/resell/listings", label: "My listings", Icon: Tag },
  { href: "/notifications", label: "Notifications", Icon: Bell },
];

const OPERATOR_NAV: NavItem[] = [
  { href: "/operator/review-queue", label: "Review", Icon: ShieldCheck },
  { href: "/returns/handle", label: "Return", Icon: RotateCcw },
  { href: "/notifications", label: "Notifications", Icon: Bell },
];

/**
 * Site nav — the real chrome (not a phone mock). Sticky header with brand,
 * role-scoped primary sections, a sign-in / sign-out control, and a mobile
 * drawer. The unread-notif count badges the bell. Hidden entirely on the auth
 * pages (/login, /register), which stand on their own without app chrome.
 */
export function SiteNav() {
  const role = useRole();
  const pathname = usePathname();
  const all = useNotifs();
  const unread = all.filter((n) => n.unread).length;
  const items = role === "operator" ? OPERATOR_NAV : CUSTOMER_NAV;
  const [open, setOpen] = useState(false);

  // Most-specific match wins, so /resell/listings highlights "My listings"
  // rather than also lighting up "Resell" (whose href is a prefix of it).
  const activeHref = items
    .filter((i) => pathname === i.href || pathname?.startsWith(i.href + "/"))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  // Close the drawer on route change.
  useEffect(() => setOpen(false), [pathname]);

  // Auth pages render without the app nav.
  if (pathname === "/login" || pathname === "/register") return null;

  return (
    <header className="sticky top-0 z-40 border-b border-hair bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-4 px-4 sm:gap-6 sm:px-6">
        <Link
          href="/"
          className="font-display text-[18px] font-extrabold uppercase tracking-tight"
          data-testid="brand"
        >
          RE<span className="text-amber-deep">BRIDGE</span>
        </Link>

        <nav className="hidden flex-1 items-center gap-1 sm:flex" data-testid="primary-nav">
          {items.map((item) => {
            const active = item.href === activeHref;
            const isNotif = item.href === "/notifications";
            return (
              <Link
                key={item.href}
                href={item.href}
                data-testid={`nav-${item.href.slice(1)}`}
                data-active={active}
                className={cn(
                  "relative flex items-center gap-2 rounded-pill px-3 py-1.5 font-sans text-[13px] font-semibold transition-colors",
                  active
                    ? "bg-ink text-white"
                    : "text-ash hover:bg-paper hover:text-ink",
                )}
              >
                <item.Icon className="h-4 w-4" />
                {item.label}
                {isNotif && unread > 0 ? (
                  <span
                    data-testid="nav-unread"
                    className="tnum ml-0.5 rounded-pill bg-amber px-1.5 text-[10px] font-bold leading-[16px] text-ink"
                  >
                    {unread}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <AuthControl />
          <button
            className="rounded-pill p-2 text-ink sm:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            data-testid="mobile-toggle"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* mobile drawer */}
      {open ? (
        <div className="border-t border-hair bg-canvas px-4 py-3 sm:hidden" data-testid="mobile-nav">
          <div className="flex flex-col gap-1">
            {items.map((item) => {
              const active = item.href === activeHref;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-card px-3 py-2.5 font-sans text-[14px] font-semibold",
                    active ? "bg-ink text-white" : "text-ash",
                  )}
                >
                  <item.Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}
    </header>
  );
}

/**
 * Auth status: signed-in shows the account email + a sign-out button; signed-out
 * shows a Sign in link. Sign-out clears the session and returns to the public
 * landing. Role is assigned at registration — there is no in-nav role toggle.
 */
function AuthControl() {
  const session = useSession();
  const router = useRouter();

  if (!session) {
    return (
      <Link href="/login" data-testid="nav-signin">
        <Button variant="secondary" size="sm">
          Sign in
        </Button>
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-2" data-testid="nav-account">
      <span className="hidden max-w-[140px] truncate text-[12px] font-semibold text-ash sm:inline">
        {session.email}
      </span>
      <button
        data-testid="nav-signout"
        onClick={() => {
          sessionStore.logout();
          window.location.href = "/";
        }}
        aria-label="Sign out"
        className="rounded-pill p-2 text-mute hover:text-ink"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}
