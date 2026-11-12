<template>
  <!-- one row of numbers, all from what get_home already sends -->
  <section
    :aria-label="__('Your numbers today')"
    class="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-outline-gray-2 bg-outline-gray-2 sm:grid-cols-4"
  >
    <div
      v-for="cell in cells"
      :key="cell.key"
      class="bg-surface-base px-4 py-4"
    >
      <p class="text-p-sm text-ink-gray-6">{{ cell.label }}</p>
      <p
        class="mt-1.5 font-mono text-2xl font-medium tabular-nums text-ink-gray-9"
      >
        {{ cell.value }}
      </p>
      <p
        class="mt-0.5 text-p-xs"
        :class="cell.alert ? 'text-danger' : 'text-ink-gray-5'"
      >
        {{ cell.hint }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import type { Company, YourDay } from "../homeMeta";

const props = defineProps<{ day: YourDay; company: Company | null }>();

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
