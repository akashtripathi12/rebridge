"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { useNotifs, useNotifsMutation, type Notif } from "@/lib/notifications";
import { cn } from "@/lib/utils";
import { Bell, Check, Gift, Sprout, Truck } from "lucide-react";

const ICONS: Record<Notif["variant"], React.ComponentType<{ className?: string }>> = {
  seller: Sprout,
  buyer: Gift,
  system: Bell,
};

const TONES: Record<Notif["variant"], string> = {
  seller: "text-trust bg-[#E7F4EC]",
  buyer: "text-amber-deep bg-[#FFF2DF]",
  system: "text-mute bg-paper",
};

function relative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function NotificationsPage() {
  const all = useNotifs();
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const unread = useMemo(() => all.filter((n) => n.unread).length, [all]);
  const shown = filter === "unread" ? all.filter((n) => n.unread) : all;

  const { markRead, markAllRead } = useNotifsMutation();

  // Mark each visible notification as read after a brief delay (typical inbox UX).
  useEffect(() => {
    const t = setTimeout(() => {
      shown.forEach((n) => {
        if (n.unread) markRead(n.id);
      });
    }, 1200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, markRead]);

  return (
    <main className="bg-canvas px-4 py-10 sm:px-6">
      <div className="mx-auto max-w-[860px]">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
              Notifications
            </div>
            <h1 className="mt-1 font-display text-[clamp(28px,4vw,40px)] font-extrabold uppercase leading-none tracking-tight">
              The routing moments
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-pill border border-hair bg-paper p-0.5 text-[11px] font-bold">
              <button
                onClick={() => setFilter("all")}
                data-testid="filter-all"
                className={cn(
                  "rounded-pill px-3 py-1",
                  filter === "all" ? "bg-ink text-white" : "text-mute",
                )}
              >
                All
              </button>
              <button
                onClick={() => setFilter("unread")}
                data-testid="filter-unread"
                className={cn(
                  "rounded-pill px-3 py-1",
                  filter === "unread" ? "bg-ink text-white" : "text-mute",
                )}
              >
                Unread{unread > 0 ? ` (${unread})` : ""}
              </button>
            </div>
            {unread > 0 && (
              <Button
                variant="ghost"
                size="sm"
                data-testid="mark-read"
                onClick={() => markAllRead()}
              >
                <Check className="h-3.5 w-3.5" /> Mark all read
              </Button>
            )}
          </div>
        </div>

        <p className="mt-3 max-w-[60ch] text-[13.5px] leading-relaxed text-ash">
          Sellers get notified when their item gets routed; buyers get notified
          when a graded match lands nearby — both sides of the loop.
        </p>

        <div
          data-testid="inbox"
          className="mt-8 divide-y divide-hair overflow-hidden rounded-card border border-hair bg-pearl"
        >
          {shown.length === 0 ? (
            <div className="grid place-items-center px-6 py-16 text-center text-[13px] text-mute">
              You&apos;re all caught up.
            </div>
          ) : (
            shown.map((n) => {
              const Icon = ICONS[n.variant];
              return (
                <Link
                  key={n.id}
                  href={n.href ?? "#"}
                  data-testid="notif"
                  data-unread={n.unread}
                  data-variant={n.variant}
                  className={cn(
                    "flex gap-3 px-5 py-4 transition-colors hover:bg-paper",
                    n.unread && "bg-paper/60",
                  )}
                  onClick={() => markRead(n.id)}
                >
                  <div
                    className={cn(
                      "grid h-10 w-10 flex-none place-items-center rounded-full",
                      TONES[n.variant],
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-sans text-[13.5px] font-bold text-ink">
                        {n.title}
                      </span>
                      {n.unread && (
                        <span className="h-1.5 w-1.5 flex-none rounded-full bg-amber" />
                      )}
                      <span className="tnum ml-auto text-[11px] text-mute">
                        {relative(n.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-[13px] leading-relaxed text-ash">
                      {n.body}
                    </p>
                  </div>
                </Link>
              );
            })
          )}
        </div>

        <div className="mt-6 rounded-card border border-dashed border-hair bg-paper px-5 py-4 text-[12.5px] text-mute">
          <div className="flex items-center gap-2 font-sans text-[11px] font-bold uppercase tracking-wider text-stone">
            <Truck className="h-3.5 w-3.5" /> About this inbox
          </div>
          <p className="mt-2 max-w-[64ch]">
            These notifications fire from the matching engine the moment an
            item is graded and routed. In the live demo, listing something on
            Resell will generate a seller notification here within a beat.
          </p>
        </div>
      </div>
    </main>
  );
}
