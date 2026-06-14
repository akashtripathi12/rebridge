import type { Config } from "tailwindcss";

/**
 * ReBridge v2 — Premium Retail tokens.
 * Source of truth: FRONTEND_INSTRUCTIONS.md + rebridge_design_reference_v2.html.
 * Rules encoded here: amber is PRICE/ACTION only, green is trust, chrome is ink.
 */
const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#111111",
        charcoal: "#39393b",
        ash: "#4b4b4d",
        mute: "#707072",
        stone: "#9e9ea0",
        hair: "#e5e5e5",
        "hair-soft": "#efeae4",
        canvas: "#F4F1EC",
        paper: "#FBFAF7",
        pearl: "#FEFDFB",
        amber: { DEFAULT: "#FF9900", deep: "#D97A00" },
        trust: { DEFAULT: "#007D48", bright: "#1EAA52" },
        sale: "#D30005",
        "ink-on-dark": "#F4F1EC",
      },
      fontFamily: {
        display: ["var(--font-archivo)", "sans-serif"],
        sans: ["var(--font-manrope)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "monospace"],
      },
      borderRadius: {
        card: "18px",
        input: "14px",
        pill: "999px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(17,17,17,.04), 0 2px 8px rgba(17,17,17,.04)",
        md: "0 8px 24px rgba(17,17,17,.08), 0 2px 6px rgba(17,17,17,.05)",
        lg: "0 30px 60px rgba(17,17,17,.16)",
      },
      transitionTimingFunction: {
        pop: "cubic-bezier(.2,1.3,.35,1)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "stage-dark":
          "linear-gradient(180deg, #000000, #000000)",
        "canvas-warm":
          "radial-gradient(120% 80% at 50% -10%, #FBF8F2 0%, #F4F1EC 55%)",
      },
      keyframes: {
        pulse2: { "50%": { opacity: "0.25" } },
        ring: {
          from: { transform: "scale(.8)", opacity: "1" },
          to: { transform: "scale(1.25)", opacity: "0" },
        },
        scan: { from: { top: "-60px" }, to: { top: "240px" } },
        rise: { to: { transform: "none" } },
        fade: { to: { opacity: "1" } },
      },
      animation: {
        pulse2: "pulse2 1s infinite",
        ring: "ring 1.8s ease-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
