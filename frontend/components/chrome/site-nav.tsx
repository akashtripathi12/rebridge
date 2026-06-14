"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell, Menu, Repeat, RotateCcw, ShieldCheck, ShoppingBag, Tag, UserCog, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRole, roleStore } from "@/lib/role";
import { useNotifs } from "@/lib/notifications";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const CUSTOMER_NAV: NavItem[] = [
  { href: "/market", label: "Market", Icon: ShoppingBag },
  { href: "/resell", label: "Resell", Icon: Repeat },
  { href: "/resell/listings", label: "My listings", Icon: Tag },
  { href: "/notifications", label: "Notifications", Icon: Bell },
];

const OPERATOR_NAV: NavItem[] = [
  { href: "/market", label: "Market", Icon: ShoppingBag },
  { href: "/resell", label: "Resell", Icon: Repeat },
  { href: "/resell/listings", label: "My listings", Icon: Tag },
  { href: "/returns/handle", label: "Return", Icon: RotateCcw },
  { href: "/notifications", label: "Notifications", Icon: Bell },
  { href: "/review", label: "Review", Icon: ShieldCheck },
];

/**
 * Site nav — the real chrome (not a phone mock). Sticky header with brand,
 * primary sections (Market / Resell / Notifications), a role switcher
 * (Customer ↔ Operator), and a mobile drawer. The unread-notif count badges the
 * bell. Role gates /review (which only appears in Operator mode), exactly as the
 * brief asks for ("a button to switch between operator and customer").
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
          <RoleSwitch />
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

function RoleSwitch() {
  const role = useRole();
  return (
    <div
      data-testid="role-switch"
      data-role={role}
      className="flex items-center gap-1 rounded-pill border border-hair bg-paper p-0.5 text-[11px] font-bold"
    >
      <button
        data-testid="role-customer"
        onClick={() => roleStore.set("customer")}
        className={cn(
          "rounded-pill px-2.5 py-1 transition-colors",
          role === "customer" ? "bg-ink text-white" : "text-mute hover:text-ink",
        )}
      >
        <span className="hidden sm:inline">Customer</span>
        <ShoppingBag className="h-3.5 w-3.5 sm:hidden" />
      </button>
      <button
        data-testid="role-operator"
        onClick={() => roleStore.set("operator")}
        className={cn(
          "flex items-center gap-1 rounded-pill px-2.5 py-1 transition-colors",
          role === "operator" ? "bg-ink text-white" : "text-mute hover:text-ink",
        )}
      >
        <span className="hidden sm:inline">Operator</span>
        <UserCog className="h-3.5 w-3.5 sm:hidden" />
      </button>
    </div>
  );
}
