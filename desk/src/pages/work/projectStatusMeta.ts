import type { Tone } from "@/components/tone";
import { __ } from "@/translation";

export interface HeldTask {
  task: string;
  subject: string;
  reason: string | null;
  since: string | null;
  days: number;
}

export interface StatusFlag {
  code: string;
  text: string;
}

export interface StatusRow {
  project: string;
  project_name: string;
  customer: string | null;
  lead: string | null;
  lead_name: string | null;
  department: string | null;
  project_status: string;
  /** the written stage; "On hold" for a paused project that has no update yet */
  stage: string | null;
  waiting_on: string | null;
  waiting_since: string | null;
  update_text: string | null;
  next_step: string | null;
  next_step_date: string | null;
  written_by_name: string | null;
  /** days since the last update; null when there never was one */
  update_age: number | null;
  stale: boolean;
  can_write: boolean;
  flags: StatusFlag[];
  facts: {
    done: number;
    total: number;
    overdue: number;
    held: HeldTask[];
    next_milestone: {
      subject: string;
      due: string | null;
      is_overdue: boolean;
    } | null;
    client_wait_days: number | null;
    last_activity: string | null;
  };
}

export interface StatusReport {
  date: string;
  stale_days: number;
  stages: string[];
  waiting_on: string[];
  rows: StatusRow[];
  can_write_any: boolean;
  ai_available: boolean;
}

/** What an update dialog and the review table edit. Who wrote it is the server's. */
export interface StatusDraft {
  project: string;
  stage: string;
  waiting_on: string;
  waiting_since: string;
  update_text: string;
  next_step: string;
  next_step_date: string;
  source: "Manual" | "AI from voice" | "AI from text";
}

/** A row the AI proposed; fields it could not tell from the text come back null. */
export interface StatusProposal {
  project: string;
  stage: string | null;
  waiting_on: string | null;
  update_text: string;
  next_step: string;
  next_step_date: string | null;
  needs_check: boolean;
}

export const NOTHING = "Nothing";
const LIVE_STAGES = ["Live", "Support"];

/** The chip's colour says how the project is doing, never the stage alone: paused is
 * gray, trouble (overdue work or a contradiction) red, a wait on the client amber, live
 * or in support green; the rest stays gray. */
export function stageTone(row: StatusRow): Tone {
  if (row.stage === "On hold") return "neutral";
  if (row.flags.length || row.facts.overdue) return "danger";
  if (row.waiting_on === "Client") return "warning";
  if (row.stage && LIVE_STAGES.includes(row.stage)) return "success";
  return "neutral";
}

export function isWaiting(row: StatusRow) {
  return !!row.waiting_on && row.waiting_on !== NOTHING;
}

export function needsAttention(row: StatusRow) {
  return !!row.flags.length || !!row.facts.overdue || row.stale;
}

/** The update as the coordinator's table shows it: one bullet per line. */
export function updateLines(row: Pick<StatusRow, "update_text">): string[] {
  return (row.update_text || "")
    .split("\n")
    .map((line) => line.replace(/^\s*[-*•]\s*/, "").trim())
    .filter(Boolean);
}

/** The computed facts as one line: done, overdue and held with their reasons. */
export function factsLine(row: StatusRow): string {
  const f = row.facts;
  const parts = [__("{0}/{1} tasks done", String(f.done), String(f.total))];
  if (f.overdue) parts.push(__("{0} overdue", String(f.overdue)));
  if (f.held.length) {
    const reasons = [...new Set(f.held.map((h) => h.reason || __("no reason")))];
    parts.push(__("{0} on hold ({1})", String(f.held.length), reasons.join(", ")));
  }
  return parts.join(" · ");
}

export function blankDraft(row: StatusRow): StatusDraft {
  return {
    project: row.project,
    stage: row.stage || "",
    waiting_on: row.waiting_on || NOTHING,
    waiting_since: row.waiting_on === NOTHING ? "" : row.waiting_since || "",
    update_text: row.update_text || "",
    next_step: row.next_step || "",
    next_step_date: row.next_step_date || "",
    source: "Manual",
  };
}

/** The AI's row on top of what the project says now: what the text did not say stays. */
export function draftFromProposal(
  row: StatusRow,
  proposal: StatusProposal,
  source: StatusDraft["source"]
): StatusDraft {
  const current = blankDraft(row);
  return {
    ...current,
    stage: proposal.stage || current.stage,
    waiting_on: proposal.waiting_on || current.waiting_on,
    waiting_since:
      proposal.waiting_on && proposal.waiting_on !== current.waiting_on
        ? ""
        : current.waiting_since,
    update_text: proposal.update_text || current.update_text,
    next_step: proposal.next_step,
    next_step_date: proposal.next_step_date || "",
    source,
  };
}
