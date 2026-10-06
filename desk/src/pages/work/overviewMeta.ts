import type { WorkItem } from "./workMeta";

export type Bucket =
  | "overdue"
  | "at_risk"
  | "due_soon"
  | "key"
  | "review"
  | "waiting_on_task"
  | "on_hold";

export const BUCKETS: Bucket[] = [
  "overdue",
  "at_risk",
  "due_soon",
  "key",
  "review",
  "waiting_on_task",
  "on_hold",
];

/** The donut's parts, most urgent first; the server counts each item under the first it is in. */
export type Urgency = "overdue" | "at_risk" | "due_soon" | "key";
export const URGENCY_ORDER: Urgency[] = ["overdue", "at_risk", "due_soon", "key"];

export type ActiveSplit = Record<Urgency | "other" | "total", number>;

export interface ProjectCount {
  project: string;
  project_name: string;
  count: number;
}

export interface AttentionItem extends WorkItem {
  /** The customer's newest work summary the user may read. */
  summary: { name: string; period_end: string } | null;
}

export interface OverviewData {
  buckets: Record<Bucket, WorkItem[]>;
  counts: Record<Bucket, number>;
  active: ActiveSplit;
  projects: ProjectCount[];
  attention: AttentionItem[];
}
