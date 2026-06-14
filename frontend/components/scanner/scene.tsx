"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, ContactShadows, RoundedBox, Html } from "@react-three/drei";
import * as THREE from "three";
import { createScanMaterial } from "./scan-material";

export interface Hotspot {
  id: string;
  label: string;
  severity: string;
  position: [number, number, number];
  revealAt: number; // scan progress 0..1 at which it pops
}

/** Map free-text defect locations to the 3 fixed model anchors (G7). */
const ANCHORS: Record<string, Omit<Hotspot, "label" | "severity" | "id">> = {
  toe: { position: [0.78, 0.4, 0.3], revealAt: 0.72 },
  sole: { position: [0.1, -0.02, 0.5], revealAt: 0.4 },
  heel: { position: [-0.82, 0.46, 0.2], revealAt: 0.58 },
};

export function defectsToHotspots(
  defects: { location: string; severity: string }[],
): Hotspot[] {
  return defects.slice(0, 3).map((d, i) => {
    const l = d.location.toLowerCase();
    let key: keyof typeof ANCHORS = "sole";
    if (l.includes("toe") || l.includes("upper") || l.includes("front")) key = "toe";
    else if (l.includes("heel") || l.includes("back")) key = "heel";
    else if (l.includes("sole") || l.includes("bottom") || l.includes("tread"))
      key = "sole";
    else key = (["toe", "sole", "heel"] as const)[i % 3];
    return {
      id: `hot-${i}`,
      label: d.location,
      severity: d.severity,
      ...ANCHORS[key],
    };
  });
}

/** Procedural sneaker placeholder (no GLB asset present). Shares the scan mat. */
function Sneaker({ material }: { material: THREE.ShaderMaterial }) {
  return (
    <group rotation={[0, -0.4, 0]}>
      {/* upper */}
      <RoundedBox args={[1.7, 0.7, 0.95]} radius={0.22} smoothness={5} position={[0, 0.42, 0]}>
        <primitive object={material} attach="material" />
      </RoundedBox>
      {/* toe box */}
      <mesh position={[0.78, 0.28, 0]}>
        <sphereGeometry args={[0.42, 32, 24]} />
        <primitive object={material} attach="material" />
      </mesh>
      {/* sole */}
      <RoundedBox args={[2.0, 0.22, 1.04]} radius={0.1} smoothness={5} position={[0, 0.02, 0]}>
        <primitive object={material} attach="material" />
      </RoundedBox>
    </group>
  );
}

/** Demand-frameloop pump: invalidates each rAF only while active+inView. */
function Pump({ active }: { active: boolean }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    const loop = () => {
      invalidate();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active, invalidate]);
  return null;
}

export function Scene({
  scanProgressRef,
  active,
  inView,
  autoRotate,
  hotspots,
  progress,
}: {
  scanProgressRef: React.MutableRefObject<number>;
  active: boolean;
  inView: boolean;
  autoRotate: boolean;
  hotspots: Hotspot[];
  progress: number;
}) {
  const material = useMemo(() => createScanMaterial(), []);

  useFrame(() => {
    material.uniforms.uScanY.value = scanProgressRef.current;
    material.uniforms.uActive.value = active || scanProgressRef.current > 0 ? 1 : 0;
  });

  const pumpActive = inView && (autoRotate || active);

  return (
    <>
      <color attach="background" args={["#0e0e10"]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[3, 6, 4]} intensity={1.1} />
      {/* amber rim light */}
      <pointLight position={[-3, 2, -3]} intensity={28} color="#ff9900" distance={14} />
      <pointLight position={[4, 1, 3]} intensity={8} color="#ffffff" distance={12} />

      <group position={[0, -0.2, 0]}>
        <Sneaker material={material} />
        <ContactShadows
          position={[0, -0.15, 0]}
          opacity={0.55}
          scale={6}
          blur={2.4}
          far={3}
          color="#000000"
        />
        {hotspots.map((h) => {
          const shown = progress >= h.revealAt;
          return (
            <group key={h.id} position={h.position}>
              {shown && (
                <Html center distanceFactor={6} zIndexRange={[20, 0]}>
                  <div data-testid="hotspot" className="scanner-hotspot">
                    <span className="dot" />
                    <span className="tag">
                      <b>{h.severity}</b> · {h.label}
                    </span>
                  </div>
                </Html>
              )}
            </group>
          );
        })}
      </group>

      <OrbitControls
        enablePan={false}
        autoRotate={autoRotate}
        autoRotateSpeed={1.1}
        enableDamping
        minPolarAngle={Math.PI / 3}
        maxPolarAngle={Math.PI / 1.8}
        minDistance={3.2}
        maxDistance={7}
      />
      <Pump active={pumpActive} />
    </>
  );
}
