import * as THREE from "three";

/**
 * The amber scan-sweep material. A single uniform `uScanY` (0→1, GSAP-driven on
 * Grade) sweeps an emissive amber band UP the mesh, with a Fresnel amber rim and
 * simple hemi lighting so the product reads on the dark studio stage.
 *
 * Implemented as a GLSL ShaderMaterial so it runs on the universal WebGL2 path
 * (and headless chromium). The WebGPU/TSL variant is a roadmap item — the visual
 * here is the intended effect; see PROGRESS.md Phase 4.
 */
export function createScanMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uScanY: { value: 0 },
      uActive: { value: 0 },
      uYMin: { value: -0.15 },
      uYMax: { value: 0.8 },
      uBase: { value: new THREE.Color("#f2efe9") },
      uAmber: { value: new THREE.Color("#ff9900") },
    },
    vertexShader: /* glsl */ `
      varying vec3 vWorldPos;
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vWorldPos = wp.xyz;
        vNormal = normalize(mat3(modelMatrix) * normal);
        vViewDir = normalize(cameraPosition - wp.xyz);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uScanY;
      uniform float uActive;
      uniform float uYMin;
      uniform float uYMax;
      uniform vec3 uBase;
      uniform vec3 uAmber;
      varying vec3 vWorldPos;
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vec3 n = normalize(vNormal);
        float ndl = clamp(dot(n, normalize(vec3(0.4, 1.0, 0.35))), 0.0, 1.0);
        vec3 col = uBase * (0.32 + 0.68 * ndl);
        // Amber Fresnel rim
        float fres = pow(1.0 - max(dot(n, normalize(vViewDir)), 0.0), 2.5);
        col += uAmber * fres * 0.55;
        // Sweeping amber band
        float scanWorldY = mix(uYMin, uYMax, uScanY);
        float d = abs(vWorldPos.y - scanWorldY);
        float band = smoothstep(0.13, 0.0, d) * uActive;
        col += uAmber * band * 1.5;
        // Subtle "already-scanned" tint below the band
        float scanned = step(vWorldPos.y, scanWorldY) * uActive;
        col = mix(col, col * 1.04 + uAmber * 0.06, scanned * 0.4);
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
}

/** True when the platform exposes WebGPU (used for the capability badge). */
export function hasWebGPU(): boolean {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}
