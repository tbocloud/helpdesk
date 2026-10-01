import { onBeforeUnmount, ref } from "vue";

/*
 * Chart colours. Categorical slots are the validated reference palette (fixed
 * order, never cycled; checked with the dataviz validator in both modes);
 * everything else comes from the TBO theme tokens so charts follow the app.
 */
const CATEGORICAL = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
};
export const MAX_CATEGORIES = CATEGORICAL.light.length;

// theme tokens are oklch(); ECharts needs colours it can parse, so resolve them to rgb
function resolveColor(cssValue: string): string {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#000";
  ctx.fillStyle = cssValue;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}

function token(name: string) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return resolveColor(value || "#888");
}

export interface ChartColors {
  dark: boolean;
  series: string[];
  other: string;
  brand: string;
  brandSoft: string;
  surface: string;
  grid: string;
  axis: string;
  textPrimary: string;
  textSecondary: string;
  danger: string;
}

function readColors(): ChartColors {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  return {
    dark,
    series: dark ? CATEGORICAL.dark : CATEGORICAL.light,
    other: token("--ink-gray-4"),
    brand: token("--brand"),
    brandSoft: token("--brand-soft"),
    surface: token("--surface-base"),
    grid: token("--outline-gray-1"),
    axis: token("--outline-gray-3"),
    textPrimary: token("--ink-gray-8"),
    textSecondary: token("--ink-gray-5"),
    danger: token("--danger"),
  };
}

/** Chart colours that follow the app's light / dark theme. */
export function useChartColors() {
  const colors = ref<ChartColors>(readColors());
  const observer = new MutationObserver(() => (colors.value = readColors()));
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  onBeforeUnmount(() => observer.disconnect());
  return colors;
}

export function escapeHtml(value: unknown) {
  const el = document.createElement("div");
  el.textContent = String(value ?? "");
  return el.innerHTML;
}

export function formatHours(hours: number | null | undefined) {
  if (hours == null) return "—";
  const rounded = Math.round(hours * 10) / 10;
  return `${rounded.toLocaleString(undefined, { maximumFractionDigits: 1 })} h`;
}

/** Shared chrome: recessive hairline grid, text tokens, value-first tooltip. */
export function baseOptions(c: ChartColors) {
  return {
    animationDuration: 300,
    textStyle: { fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif" },
    tooltip: {
      backgroundColor: c.surface,
      borderColor: c.axis,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: c.textPrimary, fontSize: 12 },
      extraCssText:
        "box-shadow: 0 4px 12px rgba(0,0,0,.08); border-radius: 8px;",
    },
  };
}

export function valueAxis(c: ChartColors, extra: Record<string, unknown> = {}) {
  return {
    type: "value",
    splitLine: { lineStyle: { color: c.grid, width: 1, type: "solid" } },
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: c.textSecondary, fontSize: 11 },
    ...extra,
  };
}

export function categoryAxis(
  c: ChartColors,
  extra: Record<string, unknown> = {}
) {
  return {
    type: "category",
    axisLine: { lineStyle: { color: c.axis } },
    axisTick: { show: false },
    axisLabel: { color: c.textSecondary, fontSize: 11 },
    ...extra,
  };
}

/** One tooltip row: a short line-key in the series colour, value first. */
export function tooltipRow(color: string, label: string, value: string) {
  return `<div style="display:flex;align-items:center;gap:8px;line-height:20px">
    <span style="display:inline-block;width:10px;height:2px;border-radius:1px;background:${color}"></span>
    <b style="font-variant-numeric:tabular-nums">${escapeHtml(value)}</b>
    <span style="opacity:.75">${escapeHtml(label)}</span></div>`;
}
