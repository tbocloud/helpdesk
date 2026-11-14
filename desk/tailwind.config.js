import frappeUIPreset from "frappe-ui/tailwind";

export default {
  presets: [frappeUIPreset],
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
    "./node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}",
    "../node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}",
    "./node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}",
    "../node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}",
  ],
  safelist: [{ pattern: /!(text|bg)-/, variants: ["hover", "active"] }],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "var(--brand)",
          hover: "var(--brand-hover)",
          soft: "var(--brand-soft)",
          ink: "var(--brand-ink)",
          on: "var(--on-brand)",
        },
        person: {
          1: "var(--person-1)",
          "1-soft": "var(--person-1-soft)",
          2: "var(--person-2)",
          "2-soft": "var(--person-2-soft)",
          3: "var(--person-3)",
          "3-soft": "var(--person-3-soft)",
          4: "var(--person-4)",
          "4-soft": "var(--person-4-soft)",
          5: "var(--person-5)",
          "5-soft": "var(--person-5-soft)",
          6: "var(--person-6)",
          "6-soft": "var(--person-6-soft)",
        },
        highlight: "var(--highlight)",
        note: {
          DEFAULT: "var(--note)",
          border: "var(--note-border)",
        },
        success: {
          DEFAULT: "var(--success)",
          soft: "var(--success-soft)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          soft: "var(--warning-soft)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          soft: "var(--danger-soft)",
        },
        info: {
          DEFAULT: "var(--info)",
          soft: "var(--info-soft)",
        },
        champion: {
          DEFAULT: "var(--champion)",
          soft: "var(--champion-soft)",
          border: "var(--champion-border)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      height: {
        18: "68px",
      },
      margin: {
        3.5: "14px",
      },
      padding: {
        2.5: "10px",
        3.5: "14px",
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
    function ({ addUtilities }) {
      addUtilities({
        ".hide-scrollbar": {
          "scrollbar-width": "none",
          "-ms-overflow-style": "none",
          "&::-webkit-scrollbar": {
            display: "none",
          },
        },
      });
    },
  ],
};
