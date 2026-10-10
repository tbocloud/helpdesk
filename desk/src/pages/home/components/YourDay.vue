<template>
  <SectionCard
    :title="__('Your day')"
    :description="__('Your open work in the order to tackle it.')"
    :to="{ name: 'MyWork' }"
    :link-label="__('My work')"
  >
    <p
      v-if="!sections.length"
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
import TaskDetailDialog, {
  type TaskAction,
  type TaskRef,
} from "@/pages/tasky/components/TaskDetailDialog.vue";
import { useApproveTask } from "@/pages/tasky/useApproveTask";
import { itemKey, type WorkItem } from "@/pages/work/workMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, watch, type Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideCoffee from "~icons/lucide/coffee";
import LucideFileText from "~icons/lucide/file-text";
import LucideFlame from "~icons/lucide/flame";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePause from "~icons/lucide/pause";
import LucidePlay from "~icons/lucide/play";
import LucideReply from "~icons/lucide/reply";
import LucideSend from "~icons/lucide/send";
import LucideTimer from "~icons/lucide/timer";
import type { DayTask, YourDay } from "../homeMeta";
import HomeItemRow from "./HomeItemRow.vue";

const props = defineProps<{ day: YourDay }>();
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
  const part = (key: Exclude<SectionKey, "files">) => ({
    count: d[key].count,
    shown: d[key].items.length,
    items: d[key].items as DayTask[],
  });
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
      to: myWork("task"),
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

// the task whose button shows a spinner while its step loads
const busy = ref<string | null>(null);

const detailTask = ref<TaskRef | null>(null);
const detailAction = ref<TaskAction | null>(null);

// the dialog closes itself once its step is done, so the spinner can stop
watch(detailTask, (task) => {
  if (task) return;
  detailAction.value = null;
  busy.value = null;
});

function openStep(item: WorkItem, action: TaskAction) {
  busy.value = item.name;
  detailAction.value = action;
  detailTask.value = {
    name: item.name,
    subject: item.title,
    project: item.project,
    project_name: item.project_name,
  };
}

function done(message: string) {
  toast.success(message);
  busy.value = null;
  emit("changed");
}

function failed(e: unknown, fallback: string) {
  toast.error(errorText(e, fallback));
  busy.value = null;
}

const start = createResource({
  url: "helpdesk.tasky.api.update_task_status",
  onSuccess: () => done(__("Started")),
  onError: (e: unknown) => failed(e, __("Couldn't start the task.")),
});

const resumeTimer = createResource({
  url: "helpdesk.tasky.api.start_timer",
  onSuccess: () => done(__("Timer resumed")),
  onError: (e: unknown) => failed(e, __("Couldn't resume the timer.")),
});

const { approve } = useApproveTask(() => {
  busy.value = null;
  emit("changed");
});

interface Action {
  label: string;
  icon: Component;
  run: (item: DayTask) => void;
}

/** One next step per task: sign it off, date it, pick it back up, start or finish it. */
function actionFor(item: DayTask, section: SectionKey): Action | null {
  if (item.kind !== "task" || section === "given_out") return null;
  if (item.status === "Pending Review") {
    return item.can_approve
      ? {
          label: __("Approve"),
          icon: LucideCheck,
          run: (task) => {
            busy.value = task.name;
            if (!approve({ name: task.name })) busy.value = null;
          },
        }
      : null;
  }
  if (item.status === "On Hold") {
    return {
      label: __("Resume"),
      icon: LucidePlay,
      run: (task) => openStep(task, "resume"),
    };
  }
  if (section === "no_date" && item.can_plan) {
    return {
      label: __("Set date"),
      icon: LucideCalendarClock,
      run: (task) => openStep(task, "plan"),
    };
  }
  if (item.timer === "paused") {
    return {
      label: __("Resume timer"),
      icon: LucidePlay,
      run: (task) => {
        busy.value = task.name;
        resumeTimer.submit({ task: task.name });
      },
    };
  }
  // the server refuses to start or finish a task while its dependency is open
  if (item.waiting_on) return null;
  if (item.status === "Open") {
    return {
      label: __("Start"),
      icon: LucidePlay,
      run: (task) => {
        busy.value = task.name;
        start.submit({ task: task.name, status: "Working" });
      },
    };
  }
  if (item.status === "Working" || item.status === "Overdue") {
    return {
      label: __("Complete"),
      icon: LucideCircleCheck,
      run: (task) => openStep(task, "complete"),
    };
  }
  return null;
}
</script>
