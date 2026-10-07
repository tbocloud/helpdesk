import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideEye from "~icons/lucide/eye";
import LucideGitMerge from "~icons/lucide/git-merge";
import LucideGitPullRequest from "~icons/lucide/git-pull-request";
import LucideGitPullRequestClosed from "~icons/lucide/git-pull-request-closed";
import LucideGitPullRequestDraft from "~icons/lucide/git-pull-request-draft";
import type { StatusMeta } from "./taskMeta";

/** A GitHub pull request linked to a task (HD Pull Request, as the task APIs return it). */
export interface TaskPullRequest {
  repo: string;
  number: number;
  title?: string;
  url?: string;
  state: string;
  review_state?: string;
  ci_state?: string;
  link_kind?: string;
}

// Labels are untranslated keys; callers pass them through __() at render time.
const PR_STATE: Record<string, StatusMeta> = {
  Open: { label: "Open", icon: LucideGitPullRequest, tone: "info" },
  Draft: { label: "Draft", icon: LucideGitPullRequestDraft, tone: "neutral" },
  Merged: { label: "Merged", icon: LucideGitMerge, tone: "success" },
  Closed: {
    label: "Closed",
    icon: LucideGitPullRequestClosed,
    tone: "neutral",
  },
};

const REVIEW_STATE: Record<string, StatusMeta> = {
  "Review requested": {
    label: "Review requested",
    icon: LucideEye,
    tone: "warning",
  },
  Approved: { label: "Approved", icon: LucideCircleCheck, tone: "success" },
  "Changes requested": {
    label: "Changes requested",
    icon: LucideCircleAlert,
    tone: "danger",
  },
};

const CI_STATE: Record<string, StatusMeta> = {
  Passing: { label: "CI passing", icon: LucideCircleCheck, tone: "success" },
  Failing: { label: "CI failing", icon: LucideCircleX, tone: "danger" },
};

export function prStateMeta(state?: string): StatusMeta {
  return PR_STATE[state ?? "Open"] ?? PR_STATE.Open;
}

/** Null when there's no review yet ("None"), so no chip is shown. */
export function prReviewMeta(state?: string): StatusMeta | null {
  return (state && REVIEW_STATE[state]) || null;
}

export function prCiMeta(state?: string): StatusMeta | null {
  return (state && CI_STATE[state]) || null;
}

/** "helpdesk#12": the repository name without the owner, like GitHub's short refs. */
export function prRef(pr: TaskPullRequest) {
  return `${pr.repo.split("/").pop()}#${pr.number}`;
}

/**
 * What a compact chip should say about the PR: the most urgent signal wins,
 * so a failing build or requested changes stand out on a crowded board.
 */
export function prSignal(pr: TaskPullRequest): {
  tone: Tone;
  icon: Component;
} {
  const ci = prCiMeta(pr.ci_state);
  if (ci?.tone === "danger") return ci;
  const review = prReviewMeta(pr.review_state);
  if (review) return review;
  return prStateMeta(pr.state);
}

/** Full sentence for tooltips and screen readers. */
export function prDescription(pr: TaskPullRequest) {
  const parts = [
    __("Pull request {0}", prRef(pr)),
    __(prStateMeta(pr.state).label),
  ];
  const review = prReviewMeta(pr.review_state);
  if (review) parts.push(__(review.label));
  const ci = prCiMeta(pr.ci_state);
  if (ci) parts.push(__(ci.label));
  return parts.join(" · ");
}
