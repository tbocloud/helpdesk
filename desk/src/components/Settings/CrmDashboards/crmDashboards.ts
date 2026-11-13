import type { MetricKind } from "@/pages/crm-dashboard/crmDashboard";
import { __ } from "@/translation";

/** What a dashboard can show, from helpdesk/crm_dashboard/registry.py (describe). */
export interface MetricInfo {
  label: string;
  kind: MetricKind;
  needs?: string;
  bases?: Record<string, { label: string; needs?: string }>;
  aggregations?: string[];
}

export interface ChartRow {
  title: string;
  enabled: 0 | 1;
  chart_type: string;
  dimension: string;
  metric: string;
  compare_metric: string;
  period: string;
  sort: string;
  max_items: number;
  width: "half" | "full";
}

export interface Registry {
  categories: string[];
  unit_types: string[];
  /** a unit type's possible parents, top down, e.g. Team: company, branch, department */
  unit_parents: Record<string, string[]>;
  dimensions: Record<string, string>;
  filters: string[];
  mapped_fields: Record<string, { label: string; kind: string }>;
  required_fields: string[];
  field_types: Record<string, string[]>;
  periods: Record<string, string>;
  scopes: Record<string, string>;
  metrics: Record<string, MetricInfo>;
  aggregations: Record<string, string>;
  chart_types: Record<string, string>;
  sorts: Record<string, string>;
  chart_presets: Record<string, Partial<ChartRow> & { title: string }>;
  templates: Record<string, { label: string; description: string }>;
}

export interface SourceSummary {
  name: string;
  enabled: 0 | 1;
  use_crm_connection: 0 | 1;
  site_url: string | null;
  last_sync_status: "" | "OK" | "Failed" | null;
  last_synced_on: string | null;
  last_full_sync_on: string | null;
  leads_synced: number;
  last_error: string | null;
  running: boolean;
}

export interface DashboardRow {
  name: string;
  dashboard_name: string;
  is_active: 0 | 1;
  is_default: 0 | 1;
  scope: string;
  template: string | null;
}

/** helpdesk.api.crm_dashboard_settings.get_settings */
export interface CrmDashboardSettingsData {
  currency: string | null;
  crm_connection: { enabled: boolean; site_url: string | null };
  registry: Registry;
  sources: SourceSummary[];
  dashboards: DashboardRow[];
  unit_count: number;
}

export interface OrgUnit {
  name: string;
  source: string;
  unit_type: string;
  unit_name: string;
  label: string;
  is_active: 0 | 1;
  origin: "Synced" | "Added here";
  company: string;
  branch: string;
  department: string;
  team: string;
  user: string | null;
  leader: string | null;
  leads: number;
}

/** The levels of the organisation, top down, with their unit type. */
export const LEVELS = [
  ["company", "Company"],
  ["branch", "Branch"],
  ["department", "Department"],
  ["team", "Team"],
  ["employee", "Employee"],
] as const;

export function unitTypeLabel(unitType: string, plural = false) {
  const labels: Record<string, [string, string]> = {
    Company: [__("Company"), __("Companies")],
    Branch: [__("Branch"), __("Branches")],
    Department: [__("Department"), __("Departments")],
    Team: [__("Team"), __("Teams")],
    Employee: [__("Employee"), __("Employees")],
  };
  return (labels[unitType] || [unitType, unitType])[plural ? 1 : 0];
}

/** {key: label} as select options, in the registry's order. */
export function optionsOf(record: Record<string, string>) {
  return Object.entries(record).map(([value, label]) => ({ label, value }));
}

/** One line on a source's last sync, for its row and its page. */
export function syncSummary(
  source: Pick<
    SourceSummary,
    | "enabled"
    | "running"
    | "last_sync_status"
    | "leads_synced"
    | "last_synced_on"
  >,
  fromNow: (date: string) => string
) {
  if (source.running) return __("Syncing now…");
  if (!source.enabled) return __("Switched off; its leads aren't counted.");
  if (!source.last_synced_on)
    return source.last_sync_status === "Failed"
      ? __("Couldn't be read yet.")
      : __("Not read yet.");
  const when = fromNow(source.last_synced_on);
  return source.last_sync_status === "Failed"
    ? __("Last read failed; {0} leads from {1}.", [source.leads_synced, when])
    : __("{0} leads, read {1}.", [source.leads_synced, when]);
}
