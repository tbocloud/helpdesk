<template>
  <SectionCard
    v-if="sections.length || !hide?.size"
    :title="__('Your day')"
    :description="__('Your open work in the order to tackle it.')"
    :to="{ name: 'MyWork' }"
    :link-label="__('My work')"
  >
    <p
      v-if="!sections.length && !hide?.size"
      class="flex items-center gap-2 px-4 py-5 text-p-sm text-ink-gray-6"
    >
      <LucideCoffee
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      {{
        __(
          "Nothing open. Work assigned to you will show up here, most urgent first."
        )
      }}
    </p>
    <div
      v-for="section in sections"
      :key="section.key"
      class="border-b border-outline-gray-2 last:border-b-0"
      role="group"
      :aria-labelledby="`${uid}-${section.key}`"
    >
      <div class="flex items-start justify-between gap-2 px-4 pb-1 pt-3">
        <div class="min-w-0">
          <h3
            :id="`${uid}-${section.key}`"
            class="flex items-center gap-2 text-sm-medium text-ink-gray-7"
          >
            <component
              :is="section.icon"
              class="size-4 shrink-0"
              :class="section.iconClass || 'text-ink-gray-5'"
              aria-hidden="true"
            />
            {{ section.label }}
            <span class="font-mono text-xs tabular-nums text-ink-gray-5">
              {{ section.count }}
            </span>
          </h3>
          <p v-if="section.hint" class="mt-0.5 text-p-xs text-ink-gray-5">
            {{ section.hint }}
          </p>
        </div>
        <RouterLink
          v-if="section.to && section.count > section.shown"
          :to="section.to"
          class="shrink-0 rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ __("See all {0}", String(section.count)) }}
        </RouterLink>
      </div>

      <ul v-if="section.key !== 'files'" role="list">
        <li v-for="item in section.items" :key="itemKey(item)">
          <HomeItemRow
            :item="item"
            :show-assigner="section.key !== 'given_out'"
            :show-assignee="section.key === 'given_out'"
          >
            <template v-if="section.key === 'waiting'" #details>
              <HoldNote
                class="mt-1"
                :note="item.hold_note"
                :by-name="item.hold_by_name"
              />
            </template>
            <template v-if="actionFor(item, section.key)" #action>
              <Button
                size="sm"
                :label="actionFor(item, section.key)!.label"
                :icon-left="actionFor(item, section.key)!.icon"
                :loading="busy === item.name"
                :aria-label="`${actionFor(item, section.key)!.label}: ${
                  item.title
                }`"
                @click="actionFor(item, section.key)!.run(item)"
              />
            </template>
          </HomeItemRow>
        </li>
      </ul>

      <ul v-else role="list">
        <li v-for="file in day.files.items" :key="file.name">
          <RouterLink
            :to="{ name: 'TaskyFiles', params: { projectId: file.project } }"
            class="flex items-start gap-3 px-4 py-3 hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
          >
            <LucideFileText
              class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1">
              <span class="block break-words text-base text-ink-gray-9">
                {{ file.file_name }}
              </span>
              <span class="mt-0.5 block text-sm text-ink-gray-5">
                {{ file.project_name }} ·
                {{ __("from {0}", file.uploaded_by_name) }}
              </span>
            </span>
            <span class="shrink-0 whitespace-nowrap text-sm text-ink-gray-6">
              {{ dayjs(file.creation).fromNow() }}
            </span>
          </RouterLink>
        </li>
      </ul>
    </div>
  </SectionCard>

  <TaskDetailDialog
    v-model:task="detailTask"
    :action="detailAction"
    @changed="emit('changed')"
  />
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import HoldNote from "@/pages/tasky/components/HoldNote.vue";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import { itemKey } from "@/pages/work/workMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, dayjs } from "frappe-ui";
import { computed, useId, type Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideCoffee from "~icons/lucide/coffee";
import LucideFileText from "~icons/lucide/file-text";
import LucideFlame from "~icons/lucide/flame";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePause from "~icons/lucide/pause";
import LucideReply from "~icons/lucide/reply";
import LucideSend from "~icons/lucide/send";
import LucideTimer from "~icons/lucide/timer";
import type { DayTask, YourDay } from "../homeMeta";
import { useDaySteps, type DayStep } from "../useDaySteps";
import HomeItemRow from "./HomeItemRow.vue";

const props = defineProps<{
  day: YourDay;
  /** Items "Do next" already lists (by itemKey), so they aren't shown twice. */
  hide?: Set<string>;
}>();
const emit = defineEmits<{ changed: [] }>();

const uid = useId();
const authStore = useAuthStore();

type SectionKey =
  | "close_first"
  | "in_progress"
  | "replies"
  | "approvals"
  | "waiting"
  | "coming_up"
  | "no_date"
  | "given_out"
  | "files";

interface Section {
  key: SectionKey;
  label: string;
  icon: Component;
  iconClass?: string;
  hint?: string;
  count: number;
  shown: number;
  items: DayTask[];
  to?: RouteLocationRaw;
}

const myWork = (tab?: string): RouteLocationRaw => ({
  name: "MyWork",
  query: tab ? { tab } : {},
});

const sections = computed<Section[]>(() => {
  const d = props.day;
  const part = (key: Exclude<SectionKey, "files">) => {
    const items = (d[key].items as DayTask[]).filter(
      (item) => !props.hide?.has(itemKey(item))
    );
    const hidden = d[key].items.length - items.length;
    return { count: d[key].count - hidden, shown: items.length, items };
  };
  const all: Section[] = [
    {
      key: "close_first",
      label: __("Close first"),
      icon: LucideFlame,
      // red only when something is actually late
      iconClass: d.summary.overdue ? "text-danger" : undefined,
      hint: __("Overdue, then due today, then key work in progress."),
      to: myWork(d.summary.overdue ? "overdue" : undefined),
      ...part("close_first"),
    },
    {
      key: "in_progress",
      label: __("In progress"),
      icon: LucideTimer,
      to: { name: "InProgress" },
      ...part("in_progress"),
    },
    {
      key: "replies",
      label: __("Waiting for your reply"),
      icon: LucideReply,
      to: myWork("ticket"),
      ...part("replies"),
    },
    {
      key: "approvals",
      label: __("Waiting for your review"),
      icon: LucideClipboardCheck,
      to: authStore.canSeeOverview
        ? { name: "WorkOverview", query: { bucket: "review" } }
        : undefined,
      ...part("approvals"),
    },
    {
      key: "waiting",
      label: __("Waiting on someone"),
      icon: LucidePause,
      hint: __("On hold or in review. Follow up so they don't stall."),
      to: myWork("task"),
      ...part("waiting"),
    },
    {
      key: "coming_up",
      label: __("Coming up in the next 7 days"),
      icon: LucideCalendarDays,
      to: myWork("task"),
      ...part("coming_up"),
    },
    {
      key: "no_date",
      label: __("No due date"),
      icon: LucideCalendarX,
      hint: d.no_date.items.some((t) => t.can_plan)
        ? __("Set a date so they don't slip out of sight.")
        : __("Ask your lead for a date so they don't slip out of sight."),
      to: myWork("task"),
      ...part("no_date"),
    },
    {
      key: "given_out",
      label: __("Tasks you gave out"),
      icon: LucideSend,
      hint: __("Overdue or waiting for review."),
      to: authStore.canSeeOverview ? { name: "WorkOverview" } : undefined,
      ...part("given_out"),
    },
    {
      key: "files",
      label: __("Files for you"),
      icon: LucidePaperclip,
      count: d.files.count,
      shown: d.files.items.length,
      items: [],
    },
  ];
  return all.filter((s) => s.count > 0);
});

const { busy, detailTask, detailAction, stepFor } = useDaySteps(() =>
  emit("changed")
);

function actionFor(item: DayTask, section: SectionKey): DayStep | null {
  if (section === "given_out") return null;
  return stepFor(item, section === "no_date");
}
</script>
