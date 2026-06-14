import { cn } from "@/lib/utils";

/**
 * PhoneFrame — the device shell used to present mobile screens (Returns Desk,
 * reveal, marketplace, Rahul flow). Matches the v2 .phone/.screen treatment.
 */
export function PhoneFrame({
  children,
  className,
  statusTime = "9:41",
  where,
  brand = true,
}: {
  children: React.ReactNode;
  className?: string;
  statusTime?: string;
  where?: string;
  brand?: boolean;
}) {
  return (
    <div
      className={cn(
        "w-full max-w-[362px] rounded-[42px] border border-[#ececec] bg-white p-[7px] shadow-lg",
        className,
      )}
    >
      <div className="relative flex min-h-[660px] flex-col overflow-hidden rounded-[36px] bg-canvas">
        <div className="flex justify-between px-[22px] pb-1.5 pt-3 font-sans text-[11px] font-semibold text-ink">
          <span className="tnum">{statusTime}</span>
          <span className="tnum tracking-tight text-mute">5G ▮▮▮ 100</span>
        </div>
        {brand || where ? (
          <div className="flex items-center gap-2.5 px-[18px] pb-3 pt-1.5">
            {brand ? (
              <div className="font-display text-[15px] font-extrabold uppercase tracking-tight">
                RE<span className="text-amber-deep">BRIDGE</span>
              </div>
            ) : null}
            {where ? (
              <div className="ml-auto rounded-pill border border-hair bg-paper px-3 py-1.5 font-sans text-[11px] font-semibold text-mute">
                {where}
              </div>
            ) : null}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}
