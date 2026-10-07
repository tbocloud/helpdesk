<template>
  <section :aria-label="__('Company pulse')" class="flex flex-col gap-2">
    <ul role="list" class="flex flex-wrap gap-2">
      <li v-for="chip in shown" :key="chip.key">
        <RouterLink
          :to="chip.to"
          class="inline-flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :class="CHIP_CLASSES[chip.tone]"
        >
          <component
            :is="chip.icon"
            class="size-4 shrink-0"
            aria-hidden="true"
          />
          <span class="font-mono font-medium tabular-nums">{{
            chip.value
          }}</span>
          <span>{{ chip.label }}</span>
          <span v-if="chip.hint" class="text-ink-gray-5"
            >· {{ chip.hint }}</span
          >
        </RouterLink>
      </li>
    </ul>
    <p
      v-if="clear.length"
      class="flex items-center gap-1.5 text-p-sm text-ink-gray-5"
    >
      <LucideCircleCheck class="size-3.5 shrink-0" aria-hidden="true" />
      {{ __("No issues: {0}", clear.join(", ")) }}
    </p>
  </section>
</template>

<script setup lang="ts">
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { computed, type Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideReply from "~icons/lucide/reply";
import LucideStar from "~icons/lucide/star";
import LucideTicket from "~icons/lucide/ticket";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUserX from "~icons/lucide/user-x";
import { overviewLink, ticketLinks, type Company } from "../homeMeta";

const props = defineProps<{ company: Company }>();

interface Chip {
  key: string;
  /** Short name used in the "No issues" line when the count is zero. */
  short: string;
  label: string;
  value: number | string;
  icon: Component;
  tone: Tone;
  hint?: string;
  to: RouteLocationRaw;
  /** A problem stat: shown only when non-zero, otherwise named in the "No issues" line. */
  problem: boolean;
  hidden?: boolean;
}

// full class strings so Tailwind's scanner keeps them
const CHIP_CLASSES: Record<Tone, string> = {
  neutral:
    "border-outline-gray-2 bg-surface-base text-ink-gray-8 hover:border-outline-gray-3",
  info: "border-transparent bg-info-soft text-info hover:border-outline-gray-3",
  warning:
    "border-transparent bg-warning-soft text-warning hover:border-outline-gray-3",
  success:
    "border-transparent bg-success-soft text-success hover:border-outline-gray-3",
  danger:
    "border-transparent bg-danger-soft text-danger hover:border-outline-gray-3",
};

const chips = computed<Chip[]>(() => {
  const c = props.company;
  const t = c.tickets;
  const w = c.work;
  const problem = (
    key: string,
    short: string,
    label: string,
    value: number,
    icon: Component,
    tone: Tone,
    to: RouteLocationRaw
  ): Chip => ({
    key,
    short,
    label,
    value,
    icon,
    tone: value ? tone : "neutral",
    to,
    problem: true,
  });
  const rating = t.rating;
  return [
    {
      key: "open",
      short: __("open tickets"),
      label: __("open tickets"),
      value: t.open,
      icon: LucideTicket,
      tone: "neutral",
      hint: t.new_today ? __("{0} new today", String(t.new_today)) : undefined,
      to: ticketLinks.open(),
      problem: false,
    },
    problem(
      "sla",
      __("SLA"),
      __("SLA breached"),
      t.sla_breached,
      LucideAlarmClock,
      "danger",
      ticketLinks.slaBreached()
    ),
    problem(
      "first_reply",
      __("first reply"),
      __("first reply overdue"),
      t.first_reply_overdue,
      LucideReply,
      "danger",
      ticketLinks.firstReplyOverdue()
    ),
    problem(
      "unassigned",
      __("unassigned tickets"),
      __("unassigned tickets"),
      t.unassigned,
      LucideUserX,
      "warning",
      ticketLinks.unassigned()
    ),
    problem(
      "overdue",
      __("overdue work"),
      __("overdue"),
      w.overdue ?? 0,
      LucideTriangleAlert,
      "danger",
      overviewLink("overdue")
    ),
    problem(
      "at_risk",
      __("work at risk"),
      __("at risk"),
      w.at_risk ?? 0,
      LucideCircleAlert,
      "warning",
      overviewLink("at_risk")
    ),
    {
      key: "projects",
      short: __("open projects"),
      label: __("open projects"),
      value: c.project_count,
      icon: LucideFolderKanban,
      tone: "neutral",
      hint: c.people_busy
        ? __("{0} people busy", String(c.people_busy))
        : undefined,
      to: { name: "TaskyProjects" },
      problem: false,
    },
    {
      key: "rating",
      short: __("ratings"),
      label: __("rating, last 30 days"),
      value: rating.average === null ? "" : `${rating.average}/5`,
      icon: LucideStar,
      tone: rating.low ? "warning" : "neutral",
      hint: rating.low
        ? __("{0} low of {1}", String(rating.low), String(rating.count))
        : __("{0} ratings", String(rating.count)),
      to: ticketLinks.rated(),
      problem: false,
      // without ratings there is nothing to say
      hidden: rating.average === null,
    },
  ];
});

const shown = computed(() =>
  chips.value.filter((c) => !c.hidden && (!c.problem || c.value))
);

const clear = computed(() =>
  chips.value.filter((c) => c.problem && !c.value).map((c) => c.short)
);
</script>
