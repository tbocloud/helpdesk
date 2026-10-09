export const CHANNELS = [
  "Instagram",
  "Facebook",
  "LinkedIn",
  "X",
  "YouTube",
  "Blog",
  "Email",
  "WhatsApp",
];
export const FORMATS = [
  "Post",
  "Carousel",
  "Reel",
  "Story",
  "Video",
  "Article",
  "Newsletter",
];
export const STATUSES = [
  "Idea",
  "Drafting",
  "Design",
  "Internal Review",
  "Client Review",
  "Changes Requested",
  "Head Review",
  "Approved",
  "Scheduled",
  "Published",
  "Cancelled",
];

// Calendar colour by workflow stage (always shown alongside the status text)
export function stageColor(status: string) {
  if (status === "Published") return "green";
  if (["Approved", "Scheduled"].includes(status)) return "violet";
  if (
    [
      "Internal Review",
      "Client Review",
      "Changes Requested",
      "Head Review",
    ].includes(status)
  )
    return "amber";
  return "blue";
}

export interface ContentPost {
  name: string;
  title: string;
  status: string;
  channel: string;
  platforms?: string;
  format?: string;
  customer: string;
  // the festival or occasion the post is for; the calendar highlights it
  special_day?: string;
  publish_on?: string;
  published_on?: string;
  published_url?: string;
  caption?: string;
  brief?: string;
  writer?: string;
  designer?: string;
  marketer?: string;
  video_editor?: string;
  writer_hours?: number;
  designer_hours?: number;
  video_editor_hours?: number;
  marketer_hours?: number;
  times_postponed?: number;
}

export const TEAM_ROLES = [
  { field: "writer", label: "Writer" },
  { field: "designer", label: "Designer" },
  { field: "video_editor", label: "Video editor" },
  { field: "marketer", label: "Digital marketer" },
] as const;

/** One person on a role, with how far they are with that role's task. */
export interface RolePerson {
  user: string;
  full_name: string;
  task?: string;
  status?: string;
  due?: string | null;
}

export type TeamRole = (typeof TEAM_ROLES)[number]["field"];
export type EntryAction =
  | "publish"
  | "postpone"
  | "cancel"
  | "assign"
  | "head_approve"
  | "head_send_back";

// the client approved; the Digital Marketing Head approves before it can go out
export const HEAD_REVIEW = "Head Review";

// Done with: never missed, never needs a reminder
export const CLOSED_STATUSES = ["Published", "Cancelled"];

export function isMissed(post: ContentPost, now = new Date()) {
  return (
    !!post.publish_on &&
    !CLOSED_STATUSES.includes(post.status) &&
    new Date(post.publish_on.replace(" ", "T")) < now
  );
}

// Not approved yet and going live within two days: the client needs chasing
const APPROVED_STATUSES = ["Approved", "Scheduled", ...CLOSED_STATUSES];
export function needsApprovalSoon(post: ContentPost, now = new Date()) {
  if (!post.publish_on || APPROVED_STATUSES.includes(post.status)) return false;
  const left =
    new Date(post.publish_on.replace(" ", "T")).getTime() - now.getTime();
  return left >= 0 && left <= 48 * 60 * 60 * 1000;
}

export interface ContentOccasion {
  date: string;
  occasion: string;
  region: string;
  idea?: string;
}

// Text Editor fields store HTML; the dialogs edit plain text
export function htmlToText(html?: string) {
  if (!html) return "";
  const el = document.createElement("div");
  el.innerHTML = html;
  return el.innerText.trim();
}

export function textToHtml(text: string) {
  if (!text.trim()) return "";
  const escape = (s: string) => {
    const el = document.createElement("div");
    el.textContent = s;
    return el.innerHTML;
  };
  return text
    .split(/\n{2,}/)
    .map((para) => `<p>${escape(para).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

// Every platform a post goes out on; older posts only have their channel
export function platformsOf(post: { channel?: string; platforms?: string }) {
  return (post.platforms || post.channel || "")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
}
