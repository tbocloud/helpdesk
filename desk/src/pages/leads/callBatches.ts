// Today's calls: the batch of leads a salesperson must call in the current slot.
// helpdesk.api.call_batches proxies TBO Smart's hub leads API (docs/leads.md).
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { createResource, toast } from "frappe-ui";
import type { LeadOptions } from "./leads";

export type CallOutcome =
  | "Connected"
  | "Not answered"
  | "Busy"
  | "Call back"
  | "Not interested"
  | "Wrong number";

/** The six answers, in the order the chips show them. `flow` outcomes ask for more first. */
export const OUTCOMES: { value: CallOutcome; label: string; flow: boolean }[] =
  [
    { value: "Connected", label: __("Connected"), flow: true },
    { value: "Not answered", label: __("Not answered"), flow: false },
    { value: "Busy", label: __("Busy"), flow: false },
    { value: "Call back", label: __("Call back"), flow: true },
    { value: "Not interested", label: __("Not interested"), flow: true },
    { value: "Wrong number", label: __("Wrong number"), flow: false },
  ];

export interface QueueLead {
  name: string;
  lead_name?: string;
  company_name?: string;
  industry?: string;
  district?: string;
  phone?: string;
  stage?: string;
  temperature?: string | null;
  last_note?: string | null;
  next_step?: string | null;
  wrong_number?: number;
}

/** One call in the queue; `item` is what an outcome is recorded against. */
export interface QueueCall {
  item: string;
  batch: string;
  slot: string;
  lead: string;
  priority: number;
  reason: string;
  is_repeat: number;
  retry_at?: string | null;
  attempts: number;
  batch_ends_at: string;
  summary: QueueLead;
}

export interface CallCounts {
  size: number;
  called: number;
  connected: number;
  pending: number;
  scheduled: number;
  overdue: number;
}

export interface MyCalls {
  available: boolean;
  enabled: boolean;
  /** why it is off, when the ERP site says */
  reason?: string;
  date?: string;
  batch?: {
    name: string;
    slot: string;
    department: string;
    starts_at: string;
    ends_at: string;
    seconds_left: number;
    batches: string[];
  } | null;
  counts?: CallCounts;
  today?: { size: number; called: number; connected: number };
  pending: QueueCall[];
  scheduled: QueueCall[];
  overdue: QueueCall[];
  can_call?: boolean;
  next_batch?: { allowed: boolean; reason?: string | null };
  next_slot?: { label: string; starts_at: string } | null;
}

export interface BatchReportPerson {
  user: string;
  user_name: string;
  department: string;
  size: number;
  called: number;
  connected: number;
  overdue: number;
  batches: {
    name: string;
    slot: string;
    status: string;
    size: number;
    called: number;
    connected: number;
    overdue: number;
  }[];
}

export interface BatchReport {
  available: boolean;
  date?: string;
  people: BatchReportPerson[];
  totals: Partial<Record<"size" | "called" | "connected" | "overdue", number>>;
}

/** "1 h 42 min left", "12 min left", "Under a minute left", "Time is up". */
export function timeLeftText(seconds: number) {
  if (seconds <= 0) return __("Time is up");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return __("Under a minute left");
  const hours = Math.floor(minutes / 60);
  if (hours < 1) return __("{0} min left", String(minutes));
  return __("{0} h {1} min left", String(hours), String(minutes % 60));
}

/** The call the person is about to make, as a dialable number. */
export function dialNumber(phone?: string | null) {
  return (phone || "").replace(/[^\d+]/g, "");
}

/** The shape of a queue after `call` got `outcome`, shown before the ERP site answers: the
 * call leaves its list, a batch call counts as called, and a retry or call back that the
 * ERP site adds is picked up by the read that follows. */
export function withOutcome(data: MyCalls, call: QueueCall): MyCalls {
  const counts = data.counts ? { ...data.counts } : undefined;
  const wasPending = data.pending.some((c) => c.item === call.item);
  const wasOverdue = data.overdue.some((c) => c.item === call.item);
  if (counts) {
    if (wasPending) counts.pending = Math.max(counts.pending - 1, 0);
    if (wasOverdue) counts.overdue = Math.max(counts.overdue - 1, 0);
    if (wasPending && !call.is_repeat) counts.called += 1;
  }
  const today = data.today ? { ...data.today } : undefined;
  if (today && wasPending && !call.is_repeat) today.called += 1;
  return {
    ...data,
    counts,
    today,
    pending: data.pending.filter((c) => c.item !== call.item),
    overdue: data.overdue.filter((c) => c.item !== call.item),
  };
}

/** One per screen, so a queue read earlier never shows before the fresh one. */
export function useMyCalls() {
  return createResource({
    url: "helpdesk.api.call_batches.get_my_calls",
  });
}

export function useRecordOutcome() {
  return createResource({
    url: "helpdesk.api.call_batches.record_call_outcome",
    method: "POST",
  });
}

export function useNextBatch() {
  return createResource({
    url: "helpdesk.api.call_batches.get_next_batch",
    method: "POST",
    onError(e: unknown) {
      toast.error(errorText(e, __("Couldn't get the next batch. Try again.")));
    },
  });
}

/** The person is a member of a department that hands out call batches: Today's calls
 * replaces Call today for them. */
export function batchesOn(options: LeadOptions | undefined) {
  return !!options?.departments?.some(
    (d) => d.is_member && d.call_batches_enabled
  );
}

export interface CallSlot {
  label: string;
  /** "HH:mm" */
  start_time: string;
  end_time: string;
  size: number | string;
}

/** A department's call-batch rules, as `get_lead_departments` carries them. */
export interface CallRules {
  call_batches_enabled: boolean;
  daily_call_cap: number | string;
  pull_unassigned: boolean;
  overdue_block_limit: number | string;
  campaign_industry: string;
  campaign_state: string;
  campaign_district: string;
  call_slots: CallSlot[];
  /** a member's own cap, replacing the department's */
  member_caps: Record<string, number | string>;
}

export const DEFAULT_RULES: CallRules = {
  call_batches_enabled: false,
  daily_call_cap: 100,
  pull_unassigned: true,
  overdue_block_limit: 10,
  campaign_industry: "",
  campaign_state: "",
  campaign_district: "",
  call_slots: [
    { label: "Morning", start_time: "10:00", end_time: "13:00", size: 50 },
    { label: "Afternoon", start_time: "14:00", end_time: "18:00", size: 50 },
  ],
  member_caps: {},
};

/** A department's rules as the form edits them (a copy): the defaults for a new one. */
export function rulesFrom(saved?: Partial<CallRules> | null): CallRules {
  const rules = JSON.parse(JSON.stringify(DEFAULT_RULES)) as CallRules;
  if (!saved?.call_slots) return rules;
  for (const key of Object.keys(rules) as (keyof CallRules)[])
    if (saved[key] !== undefined)
      (rules as Record<string, unknown>)[key] = JSON.parse(
        JSON.stringify(saved[key])
      );
  rules.call_batches_enabled = !!saved.call_batches_enabled;
  rules.pull_unassigned = !!saved.pull_unassigned;
  return rules;
}

/** What is wrong with the rules, in words, or "" when they can be saved. */
export function rulesProblem(rules: CallRules) {
  if (!rules.call_batches_enabled) return "";
  if (!rules.call_slots.length) return __("Add at least one call slot.");
  const slots = [...rules.call_slots].sort((a, b) =>
    a.start_time.localeCompare(b.start_time)
  );
  for (const slot of slots) {
    if (!slot.label.trim() || !(Math.floor(Number(slot.size)) >= 1))
      return __("Each slot needs a name and a number of calls, 1 or more.");
    if (!slot.start_time || !slot.end_time || slot.end_time <= slot.start_time)
      return __("The {0} slot has to end after it starts.", slot.label);
  }
  for (let i = 1; i < slots.length; i++)
    if (slots[i].start_time < slots[i - 1].end_time)
      return __(
        "The {0} and {1} slots overlap.",
        slots[i - 1].label,
        slots[i].label
      );
  if (!(Math.floor(Number(rules.daily_call_cap)) >= 1))
    return __("Give the daily limit a number, 1 or more.");
  return "";
}

/** The rules as the ERP site takes them. */
export function rulesPayload(rules: CallRules) {
  const caps: Record<string, number> = {};
  for (const [user, cap] of Object.entries(rules.member_caps))
    if (Math.floor(Number(cap)) >= 1) caps[user] = Math.floor(Number(cap));
  return {
    call_batches_enabled: rules.call_batches_enabled ? 1 : 0,
    daily_call_cap: Math.floor(Number(rules.daily_call_cap)) || 100,
    pull_unassigned: rules.pull_unassigned ? 1 : 0,
    overdue_block_limit: Math.max(
      Math.floor(Number(rules.overdue_block_limit)) || 0,
      0
    ),
    campaign_industry: rules.campaign_industry.trim(),
    campaign_state: rules.campaign_state.trim(),
    campaign_district: rules.campaign_district.trim(),
    call_slots: rules.call_slots.map((s) => ({
      label: s.label.trim(),
      start_time: s.start_time,
      end_time: s.end_time,
      size: Math.floor(Number(s.size)),
    })),
    member_caps: caps,
  };
}
