import { __ } from "@/translation";
import type { BusinessOverview } from "../leads";
import { FUNNEL_LABELS, monthLabel, rangeText } from "./businessFormat";

type Cell = string | number | null;

/** The page's numbers as rows of [section, item, count, amount, note], for a spreadsheet.
 * Amounts are plain numbers in the company currency. */
export function businessRows(data: BusinessOverview): Cell[][] {
  const p = data.pipeline;
  const rows: Cell[][] = [
    [__("Section"), __("Item"), __("Count"), __("Amount"), __("Note")],
    [__("Report"), __("Period"), null, null, rangeText(data)],
    [__("Report"), __("Currency"), null, null, data.currency],
    [
      __("Report"),
      __("Department"),
      null,
      null,
      data.department || __("All departments"),
    ],
    [
      __("Pipeline now"),
      __("Open clients"),
      p.count,
      p.value,
      p.weighted
        ? __("Weighted by stage probability")
        : __("Unweighted; {0} without a quotation", String(p.unpriced)),
    ],
    ...p.stages.map((s): Cell[] => [
      __("Pipeline now"),
      s.stage,
      s.count,
      s.value,
      null,
    ]),
    [
      __("Proposals"),
      __("Sent in the period"),
      data.proposals.sent.count,
      data.proposals.sent.value,
      __("{0} without a value", String(data.proposals.sent.unpriced)),
    ],
    [
      __("Proposals"),
      __("Accepted in the period"),
      data.proposals.accepted.count,
      data.proposals.accepted.value,
      null,
    ],
    [
      __("Proposals"),
      __("Declined in the period"),
      data.proposals.declined,
      null,
      null,
    ],
    [
      __("Proposals"),
      __("Acceptance rate"),
      null,
      null,
      `${data.proposals.acceptance_rate}%`,
    ],
    [
      __("Onboarding"),
      __("Clients won"),
      data.onboarding.won.count,
      data.onboarding.won.value,
      __("{0} without a value", String(data.onboarding.won.unpriced)),
    ],
    [
      __("Onboarding"),
      __("Projects started"),
      data.onboarding.projects_started,
      null,
      null,
    ],
    [__("Revenue"), __("Invoiced"), null, data.revenue.invoiced, null],
    [__("Revenue"), __("Collected"), null, data.revenue.collected, null],
    [
      __("Revenue"),
      __("Outstanding now"),
      null,
      data.revenue.outstanding,
      __("Owed by customers today, not for the period"),
    ],
    ...data.revenue.months.map((m): Cell[] => [
      __("Revenue by month"),
      monthLabel(m.month, true),
      null,
      m.invoiced,
      __("Collected: {0}", String(m.collected)),
    ]),
    ...data.funnel.map((f): Cell[] => [
      __("Funnel"),
      FUNNEL_LABELS[f.step] ?? f.step,
      f.count,
      null,
      `${f.rate}%`,
    ]),
    ...data.trend.map((m): Cell[] => [
      __("Last 6 months"),
      monthLabel(m.month, true),
      m.new,
      m.invoiced,
      __("Won: {0}; collected: {1}", String(m.won), String(m.collected)),
    ]),
    ...data.top_clients.map((c): Cell[] => [
      __("Top clients"),
      c.name,
      null,
      c.invoiced,
      null,
    ]),
    ...data.by_department.map((d): Cell[] => [
      __("By department"),
      d.label,
      d.open,
      d.invoiced,
      __(
        "Open value: {0}; won: {1} ({2}); collected: {3}",
        String(d.open_value),
        String(d.won),
        String(d.won_value),
        String(d.collected)
      ),
    ]),
  ];
  if (data.profit.available) {
    rows.push(
      [__("Profit"), __("Income"), null, data.profit.income, null],
      [__("Profit"), __("Expense"), null, data.profit.expense, null],
      [__("Profit"), __("Profit"), null, data.profit.profit, null]
    );
  }
  return rows;
}

function quote(cell: Cell) {
  const text = cell === null ? "" : String(cell);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** CSV text with a byte-order mark, so Excel reads the rupee sign and other scripts. */
export function businessCsv(data: BusinessOverview) {
  return (
    "﻿" +
    businessRows(data)
      .map((row) => row.map(quote).join(","))
      .join("\r\n")
  );
}

export function downloadCsv(data: BusinessOverview) {
  const blob = new Blob([businessCsv(data)], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `business-overview-${data.from_date}-to-${data.to_date}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
