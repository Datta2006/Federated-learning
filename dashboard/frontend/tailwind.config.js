/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#08090a",
        panel: "#0e1012",
        raise: "#14171a",
        inset: "#0a0c0e",
        line: "#23272c",
        line2: "#31373d",
        ink: {
          100: "#eceef0",
          200: "#c9ced3",
          300: "#a3abb2",
          400: "#8b949d",
          500: "#6c757e",
          600: "#525b63",
          700: "#3a424a",
        },
        accent: {
          DEFAULT: "#f5a524",
          soft: "#3a2b0d",
          dim: "#1f1706",
          text: "#ffc45e",
        },
        ok: { DEFAULT: "#7bd88f", soft: "#122417", text: "#9ce8ac" },
        warn: { DEFAULT: "#e8b04b", soft: "#2a220d", text: "#f2ca77" },
        bad: { DEFAULT: "#f07f72", soft: "#2b1512", text: "#f5a49b" },
        info: { DEFAULT: "#7cb8e8", soft: "#12212d", text: "#a5cef1" },
      },
      fontFamily: {
        sans: ["Geist Variable", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: [
          "JetBrains Mono Variable",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px", letterSpacing: "0.04em" }],
      },
      borderRadius: {
        panel: "8px",
      },
      keyframes: {
        "soft-pulse": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateY(3px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "sweep": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(220%)" },
        },
      },
      animation: {
        "soft-pulse": "soft-pulse 2s ease-in-out infinite",
        "slide-in": "slide-in 160ms ease-out both",
        sweep: "sweep 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
