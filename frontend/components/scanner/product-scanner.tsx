"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import gsap from "gsap";
import { Scene, defectsToHotspots } from "./scene";
import { hasWebGPU } from "./scan-material";
import { GradeBadge } from "@/components/ui/grade-badge";
import { ConfidenceMeter } from "@/components/ui/confidence-meter";
import { Button } from "@/components/ui/button";
import { prefersReducedMotion } from "@/lib/motion";
import type { GradeFacet } from "@/lib/schemas";

/**
 * <ProductScanner> — the 3D centerpiece. Dark studio + amber rim light, orbiting
 * procedural sneaker (GLB slot, procedural fallback). On Grade, GSAP drives the
 * amber scan sweep up the mesh; defect hotspots pop as the band passes; then the
 * GOOD badge + confidence count-up appear. Replay re-runs it.
 *
 * Renderer: universal WebGL2 (works headless + everywhere). WebGPU capability is
 * detected and shown; the WebGPU/TSL renderer is a roadmap item (PROGRESS.md).
 * frameloop="demand" + an inView pump means it never renders offscreen.
 */
export function ProductScanner({
  grade,
  autoStart = false,
}: {
  grade: GradeFacet;
  autoStart?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scanProgressRef = useRef(0);
  const [progress, setProgress] = useState(0);
  const [active, setActive] = useState(false);
  const [graded, setGraded] = useState(false);
  const [inView, setInView] = useState(true);
  // The scene renders on r3f's WebGL2 renderer (universal, headless-safe). We
  // report that truthfully and note when the platform is WebGPU-capable (the
  // WebGPU/TSL renderer is the roadmap upgrade — see PROGRESS.md Phase 4).
  const [gpuCapable] = useState(() => hasWebGPU());

  const hotspots = defectsToHotspots(grade.defects);

  // Pause rendering when scrolled offscreen.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => setInView(e.isIntersecting),
      { threshold: 0.05 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const runScan = useCallback(() => {
    if (prefersReducedMotion()) {
      scanProgressRef.current = 1;
      setProgress(1);
      setActive(true);
      setGraded(true);
      return;
    }
    setGraded(false);
    setActive(true);
    const obj = { v: 0 };
    scanProgressRef.current = 0;
    setProgress(0);
    gsap.to(obj, {
      v: 1,
      duration: 2.2,
      ease: "power1.inOut",
      onUpdate: () => {
        scanProgressRef.current = obj.v;
        setProgress(obj.v);
      },
      onComplete: () => setGraded(true),
    });
  }, []);

  const reset = useCallback(() => {
    scanProgressRef.current = 0;
    setProgress(0);
    setActive(false);
    setGraded(false);
  }, []);

  useEffect(() => {
    if (autoStart) {
      const t = setTimeout(runScan, 600);
      return () => clearTimeout(t);
    }
  }, [autoStart, runScan]);

  return (
    <div
      ref={containerRef}
      data-testid="scanner"
      className="relative aspect-square w-full overflow-hidden rounded-card bg-[#0e0e10]"
    >
      <Canvas
        frameloop="demand"
        dpr={[1, 2]}
        camera={{ position: [3.4, 1.6, 4.2], fov: 42 }}
        gl={{
          antialias: true,
          powerPreference: "high-performance",
          preserveDrawingBuffer: true,
        }}
        data-testid="scanner-canvas"
      >
        <Scene
          scanProgressRef={scanProgressRef}
          active={active}
          inView={inView}
          autoRotate={!active && !graded}
          hotspots={hotspots}
          progress={progress}
        />
      </Canvas>

      {/* Capability badge */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-pill bg-white/10 px-3 py-1.5 font-mono text-[10px] font-semibold text-white/80 backdrop-blur">
        GPU: WebGL2 {gpuCapable ? "· WebGPU-capable" : "· universal fallback"}
      </div>

      {/* Grade stamp + confidence (after scan) */}
      {graded && (
        <div
          data-testid="scanner-grade"
          className="absolute right-3 top-3 w-[180px] rounded-2xl bg-white/95 p-3 shadow-lg"
        >
          <div className="flex items-center gap-2">
            <GradeBadge grade={grade.grade} size="sm" />
            <span className="font-display text-[12px] font-bold uppercase tracking-tight text-ink">
              Graded
            </span>
          </div>
          <div className="mt-2">
            <ConfidenceMeter value={grade.confidence} showBar />
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-3 bg-gradient-to-t from-black/50 to-transparent p-4">
        {!graded ? (
          <Button
            variant="primary"
            size="sm"
            onClick={runScan}
            disabled={active}
            data-testid="scanner-grade-btn"
          >
            {active ? "Scanning…" : "Grade this product"}
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              reset();
              setTimeout(runScan, 80);
            }}
            data-testid="scanner-replay"
          >
            ↻ Replay scan
          </Button>
        )}
      </div>
    </div>
  );
}
