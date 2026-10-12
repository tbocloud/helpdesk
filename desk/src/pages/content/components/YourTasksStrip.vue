<template>
  <!-- one line over the board, calendar and sheet: the viewer's own open content tasks -->
  <button
    v-if="mine.length"
    type="button"
    class="flex min-h-[44px] w-full min-w-0 items-center gap-2.5 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-1.5 text-left text-sm transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight sm:min-h-9"
    :aria-label="__('Open your tasks. {0}', summary)"
    :title="summary"
    @click="emit('open')"
  >
    <LucideClipboardList
      class="size-4 shrink-0 text-ink-gray-5"
      aria-hidden="true"
    />
    <span
      class="line-clamp-2 min-w-0 flex-1 sm:line-clamp-1"
      aria-hidden="true"
    >
      <span class="font-medium text-ink-gray-9">{{ __("Your tasks") }}:</span
      >{{ " " }}
      <template v-for="(part, i) in counts" :key="part.key">
        <span v-if="i" class="text-ink-gray-5"> · </span>
        <span
          :class="
            part.key === 'overdue'
              ? 'font-medium text-danger'
              : 'text-ink-gray-8'
          "
          ><LucideCircleAlert
            v-if="part.key === 'overdue'"
            class="mb-0.5 mr-0.5 inline size-3.5"
          /><span class="font-mono tabular-nums">{{ part.count }}</span>
          {{ part.label }}</span
        >
      </template>
      <template v-if="next">
        <span class="text-ink-gray-5"> · </span>
        <span class="text-ink-gray-7">{{ next }}</span>
      </template>
    </span>
    <span
      class="hidden shrink-0 items-center gap-0.5 font-medium text-brand-ink sm:inline-flex"
      aria-hidden="true"
    >
      {{ __("Open") }}
      <LucideChevronRight class="size-4" />
    </span>
    <LucideChevronRight
      class="size-4 shrink-0 text-ink-gray-5 sm:hidden"
      aria-hidden="true"
    />
  </button>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import { type ContentTasksData, dueText } from "../contentTasks";

const props = defineProps<{ data?: ContentTasksData | null }>();
const emit = defineEmits<{ open: [] }>();

/** The viewer's open tasks: not done, and theirs whatever the person filter says. */
const mine = computed(() =>
  (props.data?.tasks ?? []).filter((t) => t.mine && t.stage !== "done")
);

const counts = computed(() => {
  const count = (stage: string) =>
    mine.value.filter((t) => t.stage === stage).length;
  return [
    { key: "todo", count: count("todo"), label: __("to do") },
    {
      key: "in_progress",
      count: count("in_progress"),
      label: __("in progress"),
    },
    { key: "review", count: count("review"), label: __("in review") },
    { key: "on_hold", count: count("on_hold"), label: __("on hold") },
    {
      key: "overdue",
      count: mine.value.filter((t) => t.is_overdue).length,
      label: __("overdue"),
    },
  ].filter((c) => c.count);
});

/** "next: Designer · Global Handwashing Day, due today": the soonest one to work on. */
const next = computed(() => {
  const task = mine.value
    .filter((t) => t.stage === "todo" || t.stage === "in_progress")
    .sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999"))[0];
  if (!task) return "";
  const title = props.data?.posts[task.post]?.title || task.subject;
  const due = dueText(task.due).text;
  return due
    ? __("next: {0} · {1}, {2}", __(task.role_label), title, due)
    : __("next: {0} · {1}", __(task.role_label), title);
});

const summary = computed(() =>
  [counts.value.map((c) => `${c.count} ${c.label}`).join(", "), next.value]
    .filter(Boolean)
    .join(". ")
);
</script>
