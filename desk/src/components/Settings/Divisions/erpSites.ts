import { __ } from "@/translation";

export const ERP_SITES_API = "helpdesk.api.erp_sites";
/** get_sources is read by the list and the editor; they share one copy. */
export const ERP_SITES_CACHE = "erpSites";

/** What a source maps, from helpdesk/crm_dashboard/registry.py (describe). */
export interface Registry {
  categories: string[];
  mapped_fields: Record<string, { label: string; kind: string }>;
  required_fields: string[];
  field_types: Record<string, string[]>;
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

/** helpdesk.api.erp_sites.get_sources */
export interface ErpSitesData {
  currency: string | null;
  crm_connection: { enabled: boolean; site_url: string | null };
  registry: Registry;
  /** with the names of the divisions on each */
  sources: (SourceSummary & { divisions: string[] })[];
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
  if (!source.enabled) return __("Switched off; its leads aren't read.");
  if (!source.last_synced_on)
    return source.last_sync_status === "Failed"
      ? __("Couldn't be read yet.")
      : __("Not read yet.");
  const when = fromNow(source.last_synced_on);
  return source.last_sync_status === "Failed"
    ? __(
        "Last read failed; {0} leads from {1}.",
        String(source.leads_synced),
        when
      )
    : __("{0} leads, read {1}.", String(source.leads_synced), when);
}
