import Link from "next/link";

const COLS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "For Sellers",
    links: [
      { href: "/resell", label: "Resell an item" },
      { href: "/resell/listings", label: "My listings" },
      { href: "/notifications", label: "Notifications" },
    ],
  },
  {
    title: "For Buyers",
    links: [
      { href: "/market", label: "Second Chance market" },
      { href: "/notifications", label: "Nearby matches" },
    ],
  },
  {
    title: "Trust",
    links: [
      { href: "/#how-it-works", label: "How it works" },
      { href: "/#economics", label: "Unit economics" },
      { href: "/review", label: "Operator console" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer
      className="mt-24 border-t border-hair bg-paper"
      data-testid="site-footer"
    >
      <div className="mx-auto grid max-w-[1200px] gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
        <div>
          <Link
            href="/"
            className="font-display text-[20px] font-extrabold uppercase tracking-tight"
          >
            RE<span className="text-amber-deep">BRIDGE</span>
          </Link>
          <p className="mt-3 max-w-[28ch] text-[13px] leading-relaxed text-ash">
            An AI grade, a verifiable Health Card, and an agent that finds every
            product its next owner.
          </p>
        </div>
        {COLS.map((col) => (
          <div key={col.title}>
            <div className="font-sans text-[11px] font-bold uppercase tracking-[0.16em] text-stone">
              {col.title}
            </div>
            <ul className="mt-3 flex flex-col gap-2">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    className="font-sans text-[13px] font-medium text-ash hover:text-ink"
                  >
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-hair">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-2 px-4 py-5 text-[12px] text-mute sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span className="tnum">© 2026 ReBridge · HackOn with Amazon S6</span>
          <span>Verified · HMAC-signed Health Cards · A-to-z guarantee</span>
        </div>
      </div>
    </footer>
  );
}
