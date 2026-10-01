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
    ["Internal Review", "Client Review", "Changes Requested"].includes(status)
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
  publish_on?: string;
  published_on?: string;
  published_url?: string;
  caption?: string;
  brief?: string;
  writer?: string;
  designer?: string;
  marketer?: string;
  times_postponed?: number;
}

export const TEAM_ROLES = [
  { field: "writer", label: "Writer" },
  { field: "designer", label: "Designer" },
  { field: "marketer", label: "Digital marketer" },
] as const;

export type TeamRole = (typeof TEAM_ROLES)[number]["field"];
export type EntryAction = "publish" | "postpone" | "cancel" | "assign";

// Done with: never missed, never needs a reminder
export const CLOSED_STATUSES = ["Published", "Cancelled"];

export function isMissed(post: ContentPost, now = new Date()) {
  return (
    !!post.publish_on &&
    !CLOSED_STATUSES.includes(post.status) &&
    new Date(post.publish_on.replace(" ", "T")) < now
  );
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
