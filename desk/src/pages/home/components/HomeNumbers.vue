<template>
  <!-- one row of numbers, all from what get_home already sends -->
  <section
    :aria-label="__('Your numbers today')"
    class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
  >
    <StatTile
      v-for="cell in cells"
      :key="cell.key"
      :label="cell.label"
      :value="cell.value"
      :icon="ICONS[cell.key]"
      :icon-tone="
        cell.alert ? 'danger' : cell.key === 'due_today' ? 'warning' : 'brand'
      "
    >
      <span
        class="text-[12px] tabular-nums"
        :class="cell.alert ? 'text-danger' : 'text-ink-gray-6'"
      >
        {{ cell.hint }}
      </span>
    </StatTile>
  </section>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import { __ } from "@/translation";
import { computed, type Component } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideMessageSquareReply from "~icons/lucide/message-square-reply";
import LucideTicket from "~icons/lucide/ticket";
import type { Company, YourDay } from "../homeMeta";

const props = defineProps<{ day: YourDay; company: Company | null }>();

const ICONS: Record<string, Component> = {
  open: LucideListTodo,
  due_today: LucideCalendarClock,
  replies: LucideMessageSquareReply,
  tickets: LucideTicket,
  projects: LucideFolderKanban,
};

interface Cell {
  key: string;
  label: string;
  value: number;
  hint: string;
  alert?: boolean;
}

const cells = computed<Cell[]>(() => {
  const s = props.day.summary;
  const first: Cell = {
    key: "open",
    label: __("Open work"),
    value: s.open,
    hint: s.overdue
      ? __("{0} overdue", String(s.overdue))
      : __("{0} in progress", String(s.in_progress)),
    alert: s.overdue > 0,
  };
  const dueToday: Cell = {
    key: "due_today",
    label: __("Due today"),
    value: s.due_today,
    hint: __("{0} on hold", String(s.on_hold)),
  };
  const replies: Cell = {
    key: "replies",
    label: __("Waiting for your reply"),
    value: props.day.replies.count,
    hint: __("{0} to review", String(props.day.approvals.count)),
  };
  // people who run work see the company's tickets; everyone else their own projects
  const last: Cell = props.company
    ? {
        key: "tickets",
        label: __("Open tickets"),
        value: props.company.tickets.open,
        hint: props.company.tickets.sla_breached
          ? __("{0} past SLA", String(props.company.tickets.sla_breached))
          : __("{0} new today", String(props.company.tickets.new_today)),
        alert: props.company.tickets.sla_breached > 0,
      }
    : {
        key: "projects",
        label: __("Projects"),
        value: props.day.projects.count,
        hint: __("you have open tasks in"),
      };
  return [first, dueToday, replies, last];
});
</script>
