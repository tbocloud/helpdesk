import { monthLabel } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import type { DashboardChart } from "./chartLook";
import { chart } from "./divisions";

/** The Lead status page (helpdesk.division_overview.lead_status, docs/divisions.md). */

export type LeadGroup = "Open" | "Won" | "Converted" | "Lost" | "Other";

export interface LeadCounts {
  total: number;
  open: number;
  won: number;
  converted: number;
  lost: number;
  other: number;
  conversion_rate: number | null;
}

export interface LeadStatusData {
  options: { name: string; division_name: string }[];
  currency: string | null;
  groups: LeadGroup[];
  kpis: LeadCounts & { open_value: number; won_value: number };
  divisions: (LeadCounts & {
    name: string;
    division_name: string;
    country: string;
    has_site: boolean;
    last_synced_on: string | null;
  })[];
  statuses: {
    status: string;
    group: LeadGroup;
    total: number;
    divisions: Record<string, number>;
  }[];
  people: (LeadCounts & {
    division: string;
    division_name: string;
    employee: string;
    name: string;
  })[];
  lead_sources: (LeadCounts & { lead_source: string })[];
  monthly: (LeadCounts & { month: string })[];
  filters: {
    statuses: string[];
    employees: { value: string; label: string }[];
    lead_sources: string[];
  };
}

/** A status group's meaning, always shown as a dot beside its name. */
export const GROUP_LOOK: Record<LeadGroup, { label: string; dot: string }> = {
  Open: { label: __("Open"), dot: "bg-info" },
  Won: { label: __("Won"), dot: "bg-success" },
  Converted: { label: __("Converted"), dot: "bg-success" },
  Lost: { label: __("Lost"), dot: "bg-danger" },
  Other: { label: __("Not grouped"), dot: "bg-surface-gray-5" },
};

export function leadStatusCharts(data: LeadStatusData): DashboardChart[] {
  const charts = [
    chart(
      {
        title: __("Leads by status group"),
        chart_type: "donut",
        dimension: "group",
        dimension_label: __("Status group"),
        metric: "total_leads",
        metric_label: __("Leads"),
      },
      data.groups
        .map((g) => ({
          key: g,
          label: GROUP_LOOK[g].label,
          value: data.kpis[g.toLowerCase() as keyof LeadCounts] as number,
        }))
        .filter((i) => i.value)
    ),
    chart(
      {
        title: __("Leads by status"),
        chart_type: "bar",
        dimension: "status",
        dimension_label: __("Status"),
        metric: "total_leads",
        metric_label: __("Leads"),
      },
      data.statuses.map((s) => ({
        key: s.status,
        label: s.status,
        value: s.total,
      }))
    ),
    chart(
      {
        title: __("Leads by month"),
        chart_type: "line",
        dimension: "month",
        dimension_label: __("Month"),
        metric: "total_leads",
        metric_label: __("Leads"),
        compare_metric: "won_leads",
        compare_label: __("Won or converted"),
        width: "full",
      },
      data.monthly.map((m) => ({
        key: m.month,
        label: monthLabel(m.month, true),
        value: m.total,
        compare: m.won + m.converted,
      }))
    ),
  ];
  if (data.divisions.length > 1) {
    charts.splice(
      2,
      0,
      chart(
        {
          title: __("Open, won and lost by division"),
          chart_type: "table",
          dimension: "division",
          dimension_label: __("Division"),
          metric: "total_leads",
          metric_label: __("Leads"),
          columns: [
            { metric: "total_leads", label: __("Leads"), kind: "count" },
            { metric: "open", label: __("Open"), kind: "count" },
            { metric: "won_leads", label: __("Won"), kind: "count" },
            { metric: "lost", label: __("Lost"), kind: "count" },
            {
              metric: "conversion_rate",
              label: __("Conversion"),
              kind: "percent",
            },
          ],
          width: "full",
        },
        data.divisions.map((d) => ({
          key: d.name,
          label: d.division_name,
          value: d.total,
          columns: {
            total_leads: d.total,
            open: d.open,
            won_leads: d.won + d.converted,
            lost: d.lost,
            conversion_rate: d.conversion_rate,
          },
        }))
      )
    );
  }
  return charts;
}

/** A row of the By salesperson and By lead source tables. */
export interface BreakdownRow extends LeadCounts {
  /** the filter value a click sets */
  key: string;
  id: string;
  label: string;
  division?: string;
}
