import { __ } from "@/translation";
import type { BusinessOverview } from "../leads";
import {
  type BusinessRow,
  FUNNEL_LABELS,
  fullAmount,
  monthLabel,
  shortAmount,
} from "./businessFormat";

export interface BusinessKpi {
  key: string;
  label: string;
  value: string;
  /** the full figure, for the tile's title */
  title: string;
  /** what the number covers: the period, or now */
  sub: string;
}

/** The headline numbers, each with what it covers. Shared by the page and the slides so
 * the two never disagree. */
export function businessKpis(data: BusinessOverview): BusinessKpi[] {
  const c = data.currency;
  const amount = (value: number) => ({
    value: shortAmount(value, c),
    title: fullAmount(value, c),
  });
  const { pipeline, proposals, onboarding, revenue } = data;
  return [
    {
      key: "clients",
      label: __("Clients in pipeline"),
      value: String(pipeline.count),
      title: String(pipeline.count),
      sub: __("Open now"),
    },
    {
      key: "pipeline_value",
      label: __("Pipeline value"),
      ...amount(pipeline.value),
      sub: pipeline.weighted
        ? __("Open now, weighted")
        : __("Open now, unweighted"),
    },
    {
      key: "proposals",
      label: __("Proposals sent"),
      value: String(proposals.sent.count),
      title: fullAmount(proposals.sent.value, c),
      sub: __("{0} in the period", shortAmount(proposals.sent.value, c)),
    },
    {
      key: "onboarded",
      label: __("Onboarded (won)"),
      value: String(onboarding.won.count),
      title: fullAmount(onboarding.won.value, c),
      sub: __("{0} in the period", shortAmount(onboarding.won.value, c)),
    },
    {
      key: "invoiced",
      label: __("Revenue invoiced"),
      ...amount(revenue.invoiced),
      sub: __("In the period"),
    },
    {
      key: "collected",
      label: __("Collected"),
      ...amount(revenue.collected),
      sub: __("In the period"),
    },
    {
      key: "outstanding",
      label: __("Outstanding"),
      ...amount(revenue.outstanding),
      sub: __("Owed now"),
    },
  ];
}

export function revenueChart(data: BusinessOverview) {
  const months = data.revenue.months;
  return {
    labels: months.map((m) => monthLabel(m.month, months.length > 12)),
    series: [
      { name: __("Invoiced"), values: months.map((m) => m.invoiced) },
      { name: __("Collected"), values: months.map((m) => m.collected) },
    ],
  };
}

export function trendCharts(data: BusinessOverview) {
  const labels = data.trend.map((m) => monthLabel(m.month));
  return {
    labels,
    people: [
      { name: __("New leads"), values: data.trend.map((m) => m.new) },
      { name: __("Won"), values: data.trend.map((m) => m.won) },
    ],
    money: [
      { name: __("Invoiced"), values: data.trend.map((m) => m.invoiced) },
      { name: __("Collected"), values: data.trend.map((m) => m.collected) },
    ],
  };
}

export function funnelRows(data: BusinessOverview): BusinessRow[] {
  return data.funnel.map((step) => ({
    key: step.step,
    label: FUNNEL_LABELS[step.step] ?? step.step,
    value: step.count,
    text: String(step.count),
    sub: `${step.rate}%`,
  }));
}

export function stageRows(data: BusinessOverview): BusinessRow[] {
  return data.pipeline.stages
    .filter((s) => s.count)
    .map((s) => ({
      key: s.stage,
      label: s.stage,
      value: s.count,
      text: String(s.count),
      sub: s.value ? shortAmount(s.value, data.currency) : undefined,
    }));
}

export function clientRows(data: BusinessOverview): BusinessRow[] {
  return data.top_clients.map((c) => ({
    key: c.customer,
    label: c.name,
    value: c.invoiced,
    text: shortAmount(c.invoiced, data.currency),
  }));
}

/** Facts the numbers cannot say for themselves, shown under the page and on the slides. */
export function businessNotes(data: BusinessOverview): string[] {
  const notes: string[] = [];
  if (!data.pipeline.weighted)
    notes.push(
      __(
        "Pipeline value is the latest quotation of each open client, not weighted by chance of winning."
      )
    );
  if (data.pipeline.unpriced)
    notes.push(
      __("{0} open clients have no quotation yet, so they add no value.", String(data.pipeline.unpriced))
    );
  if (data.onboarding.won.unpriced)
    notes.push(
      __(
        "{0} won clients have no quotation, deal or order amount recorded.",
        String(data.onboarding.won.unpriced)
      )
    );
  notes.push(
    __(
      "Outstanding is what customers owe today, whatever the period. Revenue is invoices posted in the period, credit notes taken off."
    )
  );
  return notes;
}
