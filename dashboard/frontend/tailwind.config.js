/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#05080d",
          900: "#080d15",
          850: "#0b111b",
          800: "#0e1622",
          750: "#121c2b",
          700: "#172335",
          600: "#203047",
          500: "#2b3e58",
        },
        mist: {
          100: "#eef4fb",
          200: "#d7e2f0",
          300: "#b4c3d8",
          400: "#8c9eb8",
          500: "#6b7d98",
          600: "#4d5f78",
        },
        signal: {
          emerald: "#34d399",
          emeraldDim: "#0f3d31",
          blue: "#60a5fa",
          blueDim: "#12294a",
          red: "#f87171",
          redDim: "#3d171a",
          amber: "#fbbf24",
          amberDim: "#3a2c0c",
          violet: "#a78bfa",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "SF Mono",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 40px -24px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(52,211,153,0.18), 0 0 32px -12px rgba(52,211,153,0.35)",
      },
      keyframes: {
        "dash-flow": {
          to: { strokeDashoffset: "-24" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.85)", opacity: "0.7" },
          "70%": { transform: "scale(1.6)", opacity: "0" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "dash-flow": "dash-flow 1.1s linear infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.2,0.6,0.3,1) infinite",
        "fade-up": "fade-up 320ms cubic-bezier(0.2,0.7,0.3,1) both",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
