<template>
  <PanelSection
    :title="__('Linked work')"
    :icon="LucideListChecks"
    :count="tasks.length || undefined"
  >
    <template #actions>
      <Button
        size="sm"
        variant="ghost"
        :label="__('New task')"
        @click="showCreateTask = true"
      >
        <template #prefix>
          <LucidePlus class="size-3.5" aria-hidden="true" />
        </template>
      </Button>
    </template>

    <div
      v-if="linked.loading && !linked.data"
      class="flex flex-col gap-2"
      aria-busy="true"
      :aria-label="__('Loading linked work')"
    >
      <div
        v-for="i in 2"
        :key="i"
        class="h-14 animate-pulse rounded-md bg-surface-gray-2"
        aria-hidden="true"
      />
    </div>

    <div
      v-else-if="linked.error && !linked.data"
      role="alert"
      class="flex flex-col items-start gap-2"
    >
      <p class="flex items-start gap-1.5 text-p-sm text-ink-gray-7">
        <LucideCircleAlert
          class="mt-0.5 size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        {{ errorText(linked.error, __("Couldn't load the linked tasks.")) }}
      </p>
      <Button size="sm" :label="__('Retry')" @click="linked.reload()" />
    </div>

    <p v-else-if="!tasks.length" class="text-p-xs text-ink-gray-5">
      {{
        __(
          "No tasks yet. Create one when this ticket needs project work; the ticket then waits on it."
        )
      }}
    </p>

    <ul v-else role="list" class="flex flex-col gap-2">
      <li
        v-for="task in tasks"
        :key="task.name"
        class="rounded-md border border-outline-gray-2"
      >
        <component
          :is="task.can_open ? NativeButton : 'div'"
          v-bind="task.can_open ? { type: 'button' } : {}"
          class="block w-full rounded-md p-2.5 text-start"
          :class="
            task.can_open &&
            'hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4'
          "
          @click="task.can_open && openTask(task)"
        >
          <span class="flex items-center justify-between gap-2">
            <span class="font-mono text-xs tabular-nums text-ink-gray-5">
              {{ task.name }}
            </span>
            <TaskStatusBadge :status="task.status" />
          </span>
          <span class="mt-1 block text-sm text-ink-gray-9">
            {{ task.subject }}
          </span>
          <span
            class="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
          >
            <span class="truncate">{{ task.project_name }}</span>
            <template v-if="task.exp_end_date">
              <span aria-hidden="true">·</span>
              <span
                class="inline-flex items-center gap-1"
                :class="isOverdue(task) && 'text-danger'"
              >
                <LucideCircleAlert
                  v-if="isOverdue(task)"
                  class="size-3.5"
                  aria-hidden="true"
                />
                {{
                  isOverdue(task)
                    ? __("Overdue, due {0}", formatDay(task.exp_end_date))
                    : __("Due {0}", formatDay(task.exp_end_date))
                }}
              </span>
            </template>
          </span>
        </component>
        <!-- links can't sit inside the task's button, so the PRs follow it -->
        <div
          v-if="task.pull_requests?.length"
          class="flex flex-wrap gap-1.5 px-2.5 pb-2.5"
        >
          <PullRequestChip
            v-for="pr in task.pull_requests"
            :key="`${pr.repo}#${pr.number}`"
            :pr="pr"
            show-repo
          />
        </div>
      </li>
    </ul>

    <CreateTaskDialog
      v-model:open="showCreateTask"
      :ticket-id="ticketId"
      :ticket-subject="ticketSubject"
      @created="onTaskCreated"
    />
    <TaskDetailDialog
      v-model:task="detailTask"
      :mine="detailMine"
      @changed="linked.reload()"
    />
  </PanelSection>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import PullRequestChip from "@/pages/tasky/components/PullRequestChip.vue";
import TaskStatusBadge from "@/pages/tasky/components/TaskStatusBadge.vue";
import type { TaskPullRequest } from "@/pages/tasky/pullRequestMeta";
import { isClosed } from "@/pages/tasky/taskMeta";
import { showCreateTask } from "@/pages/ticket/modalStates";
import { __ } from "@/translation";
import { ActivitiesSymbol, TicketSymbol } from "@/types";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, inject, onBeforeUnmount, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePlus from "~icons/lucide/plus";
import CreateTaskDialog from "./CreateTaskDialog.vue";
import PanelSection from "./PanelSection.vue";

interface LinkedTask {
  name: string;
  subject: string;
  status: string;
  project: string;
  project_name: string;
  exp_end_date?: string | null;
  mine: boolean;
  can_open: boolean;
  pull_requests?: TaskPullRequest[];
}

const props = defineProps<{ ticketId: string; ticketSubject?: string }>();

const ticket = inject(TicketSymbol)!;
const activities = inject(ActivitiesSymbol)!;

const linked = createResource({
  url: "helpdesk.api.work.get_ticket_linked_work",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: true,
});
watch(
  () => props.ticketId,
  () => linked.reload()
);

const tasks = computed<LinkedTask[]>(() => linked.data ?? []);

const detailTask = ref<LinkedTask | null>(null);
const detailMine = computed(() => !!detailTask.value?.mine);

function openTask(task: LinkedTask) {
  detailTask.value = task;
}

function isOverdue(task: LinkedTask) {
  return (
    !!task.exp_end_date &&
    !isClosed(task) &&
    dayjs(task.exp_end_date).isBefore(dayjs(), "day")
  );
}

function formatDay(date: string) {
  return dayjs(date).format("D MMM");
}

// the ticket moves to Waiting on Task and gets a comment, so refresh both
function onTaskCreated() {
  linked.reload();
  ticket.value.reload();
  activities.value?.reload();
}

// the dialog's open state is shared with the header menu; don't carry it to the next page
onBeforeUnmount(() => (showCreateTask.value = false));
</script>
