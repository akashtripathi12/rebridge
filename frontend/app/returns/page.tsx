import { ReturnsDesk } from "@/components/returns/returns-desk";
import { JourneyRail } from "@/components/journey/journey-rail";
import { itemsService } from "@/lib/services";

export default function ReturnsPage() {
  return (
    <main className="min-h-screen bg-canvas px-5 py-10">
      <div className="mx-auto max-w-[1080px]">
        <div className="font-sans text-[12px] font-bold uppercase tracking-[0.2em] text-amber-deep">
          ReBridge · 02 · Returns Desk
        </div>
        <h1 className="mt-2 font-display text-[34px] font-extrabold uppercase leading-none tracking-[-0.02em]">
          Photograph it. Grade it.
        </h1>
        <p className="mt-3 max-w-[60ch] text-[14px] leading-relaxed text-ash">
          Capture 2–4 angles of the returned item, then grade. The grade runs
          asynchronously — we poll <span className="tnum">meta.status</span> and
          reveal the result in place. <span className="tnum">{itemsService.mode}</span>{" "}
          backend.
        </p>

        <div className="mt-8">
          <JourneyRail current="capture" />
          <div className="flex justify-center">
            <ReturnsDesk />
          </div>
        </div>
      </div>
    </main>
  );
}
