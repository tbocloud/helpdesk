import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import type { Component } from "vue";
import LucideArchive from "~icons/lucide/archive";
import LucideGlobe from "~icons/lucide/globe";
import LucidePencil from "~icons/lucide/pencil";

/** An article status as a TaskyBadge: the agents' list and the article page share it. */
export const ARTICLE_STATUS: Record<
  string,
  { label: string; tone: Tone; icon: Component }
> = {
  Published: { label: __("Published"), tone: "success", icon: LucideGlobe },
  Draft: { label: __("Draft"), tone: "warning", icon: LucidePencil },
  Archived: { label: __("Archived"), tone: "neutral", icon: LucideArchive },
};

export function articleStatus(status: string) {
  return ARTICLE_STATUS[status] ?? { label: status, tone: "neutral" as Tone };
}
