"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  AdaptiveDpr,
  ContactShadows,
  Environment,
  Float,
  PresentationControls,
  Preload,
  useTexture,
} from "@react-three/drei";
import { Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

/**
 * HeroScene — the floating product object that breaks through the headline.
 *
 * A Higgsfield-generated, background-removed sneaker (restored, premium) is
 * mapped onto a billboard plane sized to its real aspect so it reads as a free
 * object — no frame, no card. It lives in actual 3D space: Float gives the
 * resting hover/breath, PresentationControls gives damped click-and-drag
 * inspection, an independent CursorTilt leans it toward the pointer with
 * inertia, and a soft ContactShadow grounds it over the warm page. The Canvas is
 * transparent, so the giant Archivo headline behind it shows through around the
 * silhouette — the reference composition.
 *
 * Only mounted client-side when motion is allowed; the reduced-motion / no-WebGL
 * path shows a static cutout in the parent instead.
 */

// Source is 1024×1024 with the shoe occupying ~the full frame. The plane uses
// that square aspect; transparent pixels carry no ink so the shoe floats free.
const PLANE = 3.7;

function ProductBillboard({ onReady }: { onReady?: () => void }) {
  // useTexture suspends until the image is decoded, so by the time this renders
  // the 3D product is genuinely on screen — safe to hand off from the still.
  const texture = useTexture("/hero/product.png");
  texture.anisotropy = 16;
  texture.colorSpace = THREE.SRGBColorSpace;
  const glow = useRadialGlow();

  useEffect(() => {
    onReady?.();
  }, [onReady]);

  return (
    <group>
      {/* Amber back-glow halo — the ReBridge accent as a soft product bloom. */}
      <mesh position={[0.1, -0.05, -0.25]} scale={[3.1, 3.1, 1]}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial
          map={glow}
          color="#FF9900"
          transparent
          opacity={0.5}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* The product itself — unlit basic material keeps the photoreal lighting. */}
      <mesh>
        <planeGeometry args={[PLANE, PLANE]} />
        <meshBasicMaterial map={texture} transparent toneMapped={false} />
      </mesh>
    </group>
  );
}

/** A soft radial-gradient sprite texture for the amber halo (built once, on GPU). */
function useRadialGlow() {
  return useMemo(() => {
    const size = 256;
    const c = document.createElement("canvas");
    c.width = c.height = size;
    const ctx = c.getContext("2d")!;
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.4, "rgba(255,255,255,0.45)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, []);
}

/**
 * Cursor-reactive tilt — independent of PresentationControls so the resting
 * pose breathes with the mouse even when no drag is happening. Inertial lerp
 * keeps it smooth, never robotic.
 */
function CursorTilt({ children }: { children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null);
  const { pointer } = useThree();
  useFrame(() => {
    if (!group.current) return;
    const targetX = pointer.y * 0.12;
    const targetY = pointer.x * 0.26;
    group.current.rotation.x += (targetX - group.current.rotation.x) * 0.05;
    group.current.rotation.y += (targetY - group.current.rotation.y) * 0.05;
  });
  return <group ref={group}>{children}</group>;
}

/**
 * Decorative orbital rings — thin amber tori drifting behind the product.
 * Reinforce the "circular / second life" idea without printing the word on the
 * page. Pure decoration; opacity stays low.
 */
function OrbitRings() {
  const a = useRef<THREE.Mesh>(null);
  const b = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (a.current) {
      a.current.rotation.z = t * 0.16;
      a.current.rotation.x = -0.95 + Math.sin(t * 0.4) * 0.05;
    }
    if (b.current) {
      b.current.rotation.z = -t * 0.1;
      b.current.rotation.x = -1.25 + Math.cos(t * 0.3) * 0.05;
    }
  });
  return (
    <group position={[0, -0.15, -0.5]}>
      <mesh ref={a}>
        <torusGeometry args={[2.0, 0.009, 16, 180]} />
        <meshBasicMaterial color="#FF9900" transparent opacity={0.28} />
      </mesh>
      <mesh ref={b}>
        <torusGeometry args={[2.5, 0.006, 16, 180]} />
        <meshBasicMaterial color="#D97A00" transparent opacity={0.16} />
      </mesh>
    </group>
  );
}

/** Gentle one-shot rise + settle when the object first appears. */
function Entrance({ children }: { children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null);
  const t = useRef(0);
  useFrame((_, delta) => {
    if (!group.current || t.current >= 1) return;
    t.current = Math.min(1, t.current + delta * 1.1);
    const e = 1 - Math.pow(1 - t.current, 3); // easeOutCubic
    group.current.position.y = (1 - e) * -0.7;
    group.current.scale.setScalar(0.9 + e * 0.1);
  });
  return <group ref={group}>{children}</group>;
}

export function HeroScene({ onReady }: { onReady?: () => void }) {
  const lights = useMemo(
    () => (
      <>
        <ambientLight intensity={0.6} />
        <directionalLight position={[3.5, 4, 4]} intensity={1.1} />
        {/* Amber rim — the ReBridge accent reading as warm product glow. */}
        <spotLight
          position={[-3.2, 1.8, 2.5]}
          angle={0.6}
          penumbra={1}
          intensity={1.4}
          color="#FF9900"
        />
        <pointLight position={[0, -2, 2]} intensity={0.3} color="#FBF8F2" />
      </>
    ),
    [],
  );

  return (
    <Canvas
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      camera={{ position: [0, 0, 5], fov: 32 }}
      style={{ background: "transparent" }}
    >
      {lights}

      <Suspense fallback={null}>
        <Entrance>
          <PresentationControls
            global
            cursor
            snap
            polar={[-0.35, 0.35]}
            azimuth={[-0.7, 0.7]}
            config={{ mass: 2.6, tension: 170, friction: 28 }}
          >
            <Float
              speed={1.15}
              rotationIntensity={0.2}
              floatIntensity={0.6}
              floatingRange={[-0.09, 0.09]}
            >
              <CursorTilt>
                <ProductBillboard onReady={onReady} />
                <OrbitRings />
              </CursorTilt>
            </Float>
          </PresentationControls>
        </Entrance>

        {/* Soft grounding shadow under the floating object. */}
        <ContactShadows
          position={[0, -1.7, 0]}
          opacity={0.4}
          scale={6}
          blur={2.8}
          far={2.4}
          color="#3a2a08"
        />
        <Environment preset="city" />
        <Preload all />
      </Suspense>

      <AdaptiveDpr pixelated />
    </Canvas>
  );
}

export default HeroScene;
