"use client";

import { useCallback, useRef } from "react";
import { Camera, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CapturedShot {
  id: string;
  file: File;
  url: string;
}

/**
 * PhotoUploader — full-page drag-drop + click-to-add capture area. 2–4 shots
 * (front / side / label). Not a phone-frame mock; this is real desktop+mobile
 * UI built for the desk and the catalogue-an-old-thing-from-home flow.
 */
export function PhotoUploader({
  shots,
  onAdd,
  onRemove,
}: {
  shots: CapturedShot[];
  onAdd: (files: FileList | File[]) => void;
  onRemove: (id: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<HTMLDivElement>(null);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragRef.current?.classList.remove("ring-amber");
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        f.type.startsWith("image/"),
      );
      if (files.length) onAdd(files);
    },
    [onAdd],
  );

  const remaining = 4 - shots.length;

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={dragRef}
        data-testid="upload-stage"
        onDragOver={(e) => {
          e.preventDefault();
          dragRef.current?.classList.add("ring-amber");
        }}
        onDragLeave={() =>
          dragRef.current?.classList.remove("ring-amber")
        }
        onDrop={onDrop}
        className="relative grid min-h-[300px] place-items-center overflow-hidden rounded-card border-2 border-dashed border-hair bg-[radial-gradient(140%_120%_at_30%_8%,#2a2a2e,#161618_60%,#0e0e10)] ring-0 ring-amber ring-offset-0 transition-shadow"
      >
        <div className="relative z-10 flex flex-col items-center gap-4 text-center text-white">
          <div className="grid h-16 w-16 place-items-center rounded-full bg-white/95 text-ink shadow-md">
            <Camera className="h-7 w-7 text-amber-deep" />
          </div>
          <div>
            <div className="font-display text-[22px] font-extrabold uppercase tracking-tight">
              Photograph the item
            </div>
            <p className="mt-1.5 max-w-[36ch] text-[13px] leading-relaxed text-white/70">
              Drag photos in, or click below. Front, side, and (if you have it) a
              label or tag. We need <span className="tnum">2–4</span>.
            </p>
          </div>
          <button
            type="button"
            data-testid="add-photo"
            disabled={remaining <= 0}
            onClick={() => fileRef.current?.click()}
            className={cn(
              "inline-flex items-center gap-2 rounded-pill px-5 py-2.5 font-sans text-[13px] font-bold transition-transform",
              remaining > 0
                ? "bg-white text-ink hover:-translate-y-0.5"
                : "cursor-not-allowed bg-white/40 text-white/60",
            )}
          >
            {shots.length === 0 ? (
              <Camera className="h-4 w-4 text-amber-deep" />
            ) : (
              <Plus className="h-4 w-4 text-amber-deep" />
            )}
            {shots.length === 0
              ? "Add first photo"
              : remaining > 0
                ? `Add another (${remaining} left)`
                : "Photo limit reached"}
          </button>
          <span className="tnum font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
            jpg · png · drag &amp; drop
          </span>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          data-testid="file-input"
          onChange={(e) => e.target.files && onAdd(e.target.files)}
        />
      </div>

      {/* Thumbnail strip */}
      <div className="grid grid-cols-4 gap-2.5" data-testid="batch-strip">
        {Array.from({ length: 4 }).map((_, i) => {
          const s = shots[i];
          return (
            <div
              key={i}
              className={cn(
                "group relative flex h-20 items-center justify-center overflow-hidden rounded-card border bg-paper",
                s ? "border-hair" : "border-dashed border-hair text-[11px] text-stone",
              )}
            >
              {s ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={s.url}
                    alt={`Shot ${i + 1}`}
                    data-testid="thumb"
                    className="h-full w-full object-cover"
                  />
                  <button
                    type="button"
                    onClick={() => onRemove(s.id)}
                    aria-label="Remove photo"
                    data-testid="remove-thumb"
                    className="absolute right-1 top-1 grid h-5 w-5 place-items-center rounded-full bg-ink/80 text-white opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </>
              ) : (
                <span className="tnum">{i + 1}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
