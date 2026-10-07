<template>
  <SectionCard
    :title="__('Your day')"
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
        __("Nothing due today. Nothing is waiting for your reply or review.")
      }}
    </p>
    <div
      v-for="section in sections"
      :key="section.key"
      class="border-b border-outline-gray-2 last:border-b-0"
      role="group"
      :aria-labelledby="`${uid}-${section.key}`"
    >
      <div class="flex items-center justify-between gap-2 px-4 pb-1 pt-3">
        <h3
          :id="`${uid}-${section.key}`"
          class="flex items-center gap-2 text-sm-medium text-ink-gray-7"
        >
          <component
            :is="section.icon"
            class="size-4 text-ink-gray-5"
            aria-hidden="true"
          />
          {{ section.label }}
          <span class="font-mono text-xs tabular-nums text-ink-gray-5">
            {{ section.count }}
          </span>
        </h3>
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
          <HomeItemRow :item="item">
            <template v-if="actionFor(item)" #action>
              <Button
                size="sm"
                :label="actionFor(item)!.label"
                :icon-left="actionFor(item)!.icon"
                :loading="busy === item.name"
                :aria-label="`${actionFor(item)!.label}: ${item.title}`"
                @click="actionFor(item)!.run(item)"
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

  <CompleteTaskDialog
    v-model:task="completingTask"
    @completed="emit('changed')"
  />
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import CompleteTaskDialog from "@/pages/tasky/components/CompleteTaskDialog.vue";
import { useApproveTask } from "@/pages/tasky/useApproveTask";
import { itemKey, type WorkItem } from "@/pages/work/workMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, createResource, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, type Component } from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideCoffee from "~icons/lucide/coffee";
import LucideFileText from "~icons/lucide/file-text";
import LucideListTodo from "~icons/lucide/list-todo";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePlay from "~icons/lucide/play";
import LucideReply from "~icons/lucide/reply";
import type { YourDay } from "../homeMeta";
import SectionCard from "@/components/SectionCard.vue";
import HomeItemRow from "./HomeItemRow.vue";

const props = defineProps<{ day: YourDay }>();
const emit = defineEmits<{ changed: [] }>();

const uid = useId();
const authStore = useAuthStore();

interface Section {
  key: "tasks" | "replies" | "approvals" | "files";
  label: string;
  icon: Component;
  count: number;
  shown: number;
  items: WorkItem[];
  to?: RouteLocationRaw;
}

const sections = computed<Section[]>(() => {
  const d = props.day;
  const all: Section[] = [
    {
      key: "tasks",
      label: __("Due today, overdue or at risk"),
      icon: LucideListTodo,
      count: d.tasks.count,
      shown: d.tasks.items.length,
      items: d.tasks.items,
      to: { name: "MyWork" },
    },
    {
      key: "replies",
      label: __("Waiting for your reply"),
      icon: LucideReply,
      count: d.replies.count,
      shown: d.replies.items.length,
      items: d.replies.items,
      to: { name: "MyWork" },
    },
    {
      key: "approvals",
      label: __("Waiting for your review"),
      icon: LucideClipboardCheck,
      count: d.approvals.count,
      shown: d.approvals.items.length,
      items: d.approvals.items,
      to: authStore.canSeeOverview
        ? { name: "WorkOverview", query: { bucket: "review" } }
        : undefined,
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

// the task currently being started or approved, for the button's spinner
const busy = ref<string | null>(null);

const start = createResource({
  url: "helpdesk.tasky.api.update_task_status",
  onSuccess() {
    toast.success(__("Started"));
    busy.value = null;
    emit("changed");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't start the task.")));
    busy.value = null;
  },
});

const { approve } = useApproveTask(() => {
  busy.value = null;
  emit("changed");
});

const completing = ref<WorkItem | null>(null);
const completingTask = computed({
  get: () =>
    completing.value
      ? { name: completing.value.name, subject: completing.value.title }
      : null,
  set: (value) => {
    if (!value) completing.value = null;
  },
});

interface Action {
  label: string;
  icon: Component;
  run: (item: WorkItem) => void;
}

// one next step per task: start it, finish it, or sign it off
function actionFor(item: WorkItem): Action | null {
  if (item.kind !== "task") return null;
  if (item.status === "Pending Review") {
    return item.can_approve
      ? {
          label: __("Approve"),
          icon: LucideCheck,
          run: (task) => {
            busy.value = task.name;
            approve({ name: task.name });
          },
        }
      : null;
  }
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
      run: (task) => {
        completing.value = task;
      },
    };
  }
  return null;
}
</script>
