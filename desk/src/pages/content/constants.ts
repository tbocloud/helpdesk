export const CHANNELS = ["Instagram", "Facebook", "LinkedIn", "X", "YouTube", "Blog", "Email", "WhatsApp"];
export const FORMATS = ["Post", "Carousel", "Reel", "Story", "Video", "Article", "Newsletter"];
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
];

// Calendar colour by workflow stage (always shown alongside the status text)
export function stageColor(status: string) {
  if (status === "Published") return "green";
  if (["Approved", "Scheduled"].includes(status)) return "violet";
  if (["Internal Review", "Client Review", "Changes Requested"].includes(status)) return "amber";
  return "blue";
}
