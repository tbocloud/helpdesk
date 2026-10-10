<template>
  <!-- the title's link covers the row (::after); the action sits above it -->
  <div
    class="relative flex items-start gap-3 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-within:bg-surface-gray-1"
  >
    <component
      :is="item.kind === 'ticket' ? LucideTicket : LucideSquareCheck"
      class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
      aria-hidden="true"
    />
    <div class="min-w-0 flex-1">
      <span class="sr-only">{{
        item.kind === "ticket" ? __("Ticket") : __("Task")
      }}</span>
      <RouterLink
        v-if="to"
        :to="to"
        class="line-clamp-2 break-words rounded-sm text-base text-ink-gray-9 after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :title="item.title"
      >
        {{ item.title }}
      </RouterLink>
      <span v-else class="line-clamp-2 break-words text-base text-ink-gray-9">
        {{ item.title }}
      </span>
      <div
        class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm text-ink-gray-5"
      >
        <template v-for="(part, index) in meta" :key="index">
          <span v-if="index" aria-hidden="true">·</span>
          <span :class="part.mono ? 'font-mono text-xs tabular-nums' : ''">
            {{ part.text }}
          </span>
        </template>
        <template v-if="item.is_key">
          <span aria-hidden="true">·</span>
          <span class="inline-flex items-center gap-1 text-warning">
            <LucideStar class="size-3 fill-current" aria-hidden="true" />
            {{ __("Key") }}
          </span>
        </template>
      </div>
      <p
        v-if="note"
        class="mt-1 flex items-start gap-1 text-xs"
        :class="note.tone === 'warning' ? 'text-warning' : 'text-ink-gray-6'"
      >
        <component
          :is="note.icon"
          class="mt-px size-3 shrink-0"
          aria-hidden="true"
        />
        <span>{{ note.text }}</span>
      </p>
      <slot name="details" />
    </div>
    <div
      class="flex shrink-0 flex-col items-end gap-2 sm:flex-row sm:items-center sm:gap-3"
    >
      <span
        class="inline-flex items-center gap-1 whitespace-nowrap text-sm tabular-nums"
        :class="
          deadline.overdue ? 'font-medium text-danger' : 'text-ink-gray-6'
        "
        :title="deadlineTitle"
      >
        <LucideAlarmClock
          v-if="deadline.overdue"
          class="size-3.5 shrink-0"
          aria-hidden="true"
        />
        {{ deadline.label }}
      </span>
      <div v-if="$slots.action" class="relative z-10">
        <slot name="action" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { deadlineInfo, itemRoute } from "@/pages/work/workMeta";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideStar from "~icons/lucide/star";
import LucideTicket from "~icons/lucide/ticket";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucidePause from "~icons/lucide/pause";
import LucideTimer from "~icons/lucide/timer";
import { countLabel, type AttentionItem, type DayTask } from "../homeMeta";

const props = defineProps<{
  item: AttentionItem & DayTask;
  /** Name the assignee (or say it's unassigned); off in the user's own lists. */
  showAssignee?: boolean;
  /** Say who gave the user this task. */
  showAssigner?: boolean;
}>();

const userStore = useUserStore();

const to = computed(() => itemRoute(props.item));
const deadline = computed(() => deadlineInfo(props.item));

const deadlineTitle = computed(() => {
  if (!props.item.deadline) return undefined;
  return props.item.kind === "ticket"
    ? dayjs(props.item.deadline).format("D MMM YYYY, h:mm A")
    : dayjs(props.item.deadline).format("D MMM YYYY");
});

function fullName(user: string) {
  return userStore.getUser(user)?.full_name || user;
}

const meta = computed(() => {
  const item = props.item;
  const parts: { text: string; mono?: boolean }[] = [];
  const context =
    item.kind === "ticket"
      ? item.customer
      : [item.project_name || item.project, item.customer]
          .filter(Boolean)
          .filter((v, i, all) => all.indexOf(v) === i)
          .join(" · ");
  if (context) parts.push({ text: context });
  parts.push({
    text: item.kind === "ticket" ? `#${item.name}` : item.name,
    mono: true,
  });
  if (props.showAssigner && item.assigned_by_name)
    parts.push({ text: __("Assigned by {0}", item.assigned_by_name) });
  if (props.showAssignee) {
    const [first, ...rest] = item.assignees;
    parts.push({
      text: first
        ? rest.length
          ? `${fullName(first)} +${rest.length}`
          : fullName(first)
        : __("Unassigned"),
    });
  }
  return parts;
});

const note = computed(() => {
  const item = props.item;
  if (item.waiting_days !== undefined) {
    return {
      tone: "neutral",
      icon: LucideHourglass,
      text: countLabel(
        item.waiting_days,
        __("We replied 1 day ago"),
        __("We replied {0} days ago")
      ),
    };
  }
  if (item.status === "On Hold" && item.hold_reason) {
    return { tone: "neutral", icon: LucidePause, text: holdText(item) };
  }
  if (item.kind === "task" && item.status === "Pending Review") {
    return {
      tone: "neutral",
      icon: LucidePause,
      text: __("Waiting for a lead or manager to review it"),
    };
  }
  if (item.timer) {
    return {
      tone: "neutral",
      icon: LucideTimer,
      text:
        item.timer === "running"
          ? __("Timer running")
          : __("Timer paused: resume when you pick it up"),
    };
  }
  if (item.risks?.length) {
    return {
      tone: "warning",
      icon: LucideTriangleAlert,
      text: item.risks.join(" · "),
    };
  }
  return null;
});

// the hint names the next step for the holds the user can chase
const NEXT_STEP: Record<string, string> = {
  "Waiting on customer": __("follow up"),
  "Waiting on another task": __("check on it"),
};

function holdText(item: DayTask) {
  const reason = item.hold_reason || "";
  const days = item.hold_days ?? 0;
  const held =
    days > 1
      ? __("{0} for {1} days", reason, String(days))
      : days === 1
      ? __("{0} for 1 day", reason)
      : __("{0} since today", reason);
  const next = NEXT_STEP[reason];
  return next ? `${held} · ${next}` : held;
}
</script>
