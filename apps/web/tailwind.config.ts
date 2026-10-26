import type { Config } from "tailwindcss";

// These mirror packages/shared-types/schema/contracts.json. Kept inline so the Tailwind
// build never depends on resolving the workspace TS package at config-load time.
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0B0F14",
        surface: "#121821",
        raised: "#1A2230",
        border: "#243042",
        text: "#E6EDF3",
        muted: "#8B98A9",
        accent: {
          DEFAULT: "#3B82F6",
          fg: "#0B0F14",
        },
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444",
        // entity-type hues
        entity: {
          domain: "#38BDF8",
          subdomain: "#0EA5E9",
          ip: "#A78BFA",
          email: "#F472B6",
          username: "#34D399",
          person: "#FBBF24",
          organization: "#F87171",
          phone: "#2DD4BF",
          url: "#60A5FA",
          asn: "#C084FC",
          certificate: "#4ADE80",
          social: "#F0ABFC",
          breach: "#FB7185",
          hash: "#94A3B8",
          location: "#FCD34D",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["12px", { lineHeight: "16px" }],
        sm: ["14px", { lineHeight: "20px" }],
        base: ["16px", { lineHeight: "24px" }],
        lg: ["20px", { lineHeight: "28px", letterSpacing: "-0.01em" }],
        xl: ["28px", { lineHeight: "34px", letterSpacing: "-0.02em" }],
        "2xl": ["36px", { lineHeight: "42px", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        lg: "12px",
        md: "8px",
        sm: "6px",
      },
      spacing: {
        "4.5": "18px",
      },
      boxShadow: {
        focus: "0 0 0 1px #243042, 0 0 0 3px rgba(59,130,246,0.25)",
        glow: "0 0 24px rgba(59,130,246,0.18)",
        drawer: "-12px 0 40px rgba(0,0,0,0.45)",
        card: "0 1px 2px rgba(0,0,0,0.4)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        "slide-up": "slide-up 180ms ease-out",
        "slide-in-right": "slide-in-right 200ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
