import type { TeamRole } from "@/pages/content/constants";
import type { WorkItem } from "./workMeta";

/** How the In progress page groups its lanes (`helpdesk.api.in_progress`). */
export const IN_PROGRESS_GROUPS = ["project", "person", "department"] as const;
export type InProgressGroup = (typeof IN_PROGRESS_GROUPS)[number];

/** A started task: Working, Pending Review or On Hold. */
export interface InProgressTask extends WorkItem {
  kind: "task";
  department?: string | null;
  assignee_names: Record<string, string>;
  estimated_hours: number;
  custom_timer_start: string | null;
  custom_timer_elapsed: number;
}

/** A part of a post that still waits on its people in the post's stage. */
export interface PendingPart {
  role: TeamRole;
  label: string;
  people: { user: string; full_name: string }[];
  task: string | null;
  task_status: string | null;
  due: string | null;
}

/** A content post in production (Drafting to Approved, not yet published). */
export interface InProgressPost {
  kind: "post";
  name: string;
  title: string;
  customer: string | null;
  status: string;
  publish_on: string | null;
  platforms: string[];
  format?: string | null;
  pending: PendingPart[];
  /** Internal review, the client's or the head's approval: no one's part. */
  waiting_on: string | null;
  is_missed: boolean;
  /** Not approved yet and going live within two days. */
  at_risk: boolean;
}

export interface InProgressCounts {
  in_progress: number;
  review: number;
  on_hold: number;
  overdue: number;
  escalated: number;
  posts: number;
  missed: number;
  at_risk: number;
}

export interface InProgressLane {
  key: string;
  kind: InProgressGroup | "content";
  title: string;
  /** The project's customer. */
  subtitle: string | null;
  tasks: InProgressTask[];
  posts: InProgressPost[];
  counts: InProgressCounts;
}

export interface InProgressData {
  /** "own": the viewer runs no project, so the lists hold only their own work. */
  scope: "team" | "own";
  group_by: InProgressGroup;
  summary: InProgressCounts;
  lanes: InProgressLane[];
  truncated: boolean;
}
