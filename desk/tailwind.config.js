import frappeUIPreset from "frappe-ui/tailwind";
import { readFileSync } from "node:fs";

/*
 * A compact type scale (2026-11-14, the owner found frappe-ui's text too big):
 * each step is about 1px smaller and the letter-spacing frappe-ui adds is
 * dropped, since Geist is already wide. frappe-ui builds the plain sizes from
 * the theme and the weighted ones (text-base-medium…) in its plugin, so the
 * theme gets the plain sizes and the plugin below re-emits the weighted ones;
 * it is registered after the preset's, so its rules come later and win.
 */
const typography = JSON.parse(
  readFileSync(
    new URL(
      "./node_modules/frappe-ui/tailwind/generated/typography.json",
      import.meta.url
    ),
    "utf8"
  )
);
const COMPACT = {
  "2xs": "10.5px",
  xs: "11.5px",
  sm: "12.5px",
  base: "13px",
  md: "14px",
  lg: "15px",
  xl: "16px",
  "2xl": "17px",
  "3xl": "19px",
};
const WEIGHTS = ["medium", "semibold", "bold", "black"];
const compactSize = Object.fromEntries(
  Object.entries(COMPACT).flatMap(([key, size]) => {
    const meta = typography.fontSize[key][1];
    const para = typography.paragraph[key];
    return [
      [key, [size, { ...meta, letterSpacing: "0" }]],
      ...(para
        ? [
            [
              `p-${key}`,
              [
                size,
                { ...meta, lineHeight: para.lineHeight, letterSpacing: "0" },
              ],
            ],
          ]
        : []),
    ];
  })
);
const compactWeights = {};
for (const [key, size] of Object.entries(COMPACT)) {
  const groups = [
    [
      `.text-${key}`,
      typography.tracking.text?.[key],
      typography.fontSize[key][1].lineHeight,
    ],
    [
      `.text-p-${key}`,
      typography.tracking.paragraph?.[key],
      typography.paragraph[key]?.lineHeight,
    ],
  ];
  for (const [base, byWeight, lineHeight] of groups) {
    if (!byWeight || !lineHeight) continue;
    for (const weight of WEIGHTS)
      if (weight in byWeight)
        compactWeights[`${base}-${weight}`] = {
          fontSize: size,
          lineHeight,
          fontWeight: String(typography.fontWeight[weight]),
          letterSpacing: "0",
        };
  }
}

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
          "ink-hover": "var(--brand-ink-hover)",
          "soft-border": "var(--brand-soft-border)",
          on: "var(--on-brand)",
        },
        canvas: "var(--surface-canvas)",
        violet: {
          DEFAULT: "var(--violet)",
          soft: "var(--violet-soft)",
        },
        hot: {
          DEFAULT: "var(--hot)",
          fill: "var(--hot-fill)",
        },
        "warm-fill": "var(--warm-fill)",
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
          panel: "var(--warning-panel)",
          border: "var(--warning-border)",
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
      fontSize: compactSize,
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
      addUtilities(compactWeights);
    },
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
