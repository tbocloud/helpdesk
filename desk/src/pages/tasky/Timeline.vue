<template>
  <div class="flex h-full flex-col">
    <ProjectNav
      :project-id="projectId"
      :phases="phaseNames"
      @task-created="tasks.reload()"
    >
      <template #actions>
        <Button
          size="md"
          :label="__('Refresh')"
          :loading="tasks.loading && !!tasks.data"
          @click="tasks.reload()"
        >
          <template #icon
            ><LucideRefreshCw class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="tasks.error && !tasks.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the timeline')"
          :message="loadErrorMessage(tasks.error)"
        >
          <Button :label="__('Retry')" @click="tasks.reload()" />
        </TaskyState>

        <div
          v-else
          class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        >
          <div
            class="hidden h-11 grid-cols-[1fr_9rem_8rem_7rem] items-center gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-5 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6 md:grid"
          >
            <span>{{ __("Task") }}</span>
            <span>{{ __("Phase") }}</span>
            <span>{{ __("Status") }}</span>
            <span class="text-right">{{ __("Due") }}</span>
          </div>

          <!-- Loading -->
          <template v-if="!tasks.data">
            <div
              v-for="i in 6"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
              aria-hidden="true"
            >
              <div class="size-4 animate-pulse rounded bg-surface-gray-3" />
              <div
                class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-3"
              />
              <div
                class="ml-auto h-3 w-16 animate-pulse rounded bg-surface-gray-3"
              />
            </div>
          </template>

          <!-- Empty -->
          <TaskyState
            v-else-if="!sortedTasks.length"
            class="py-10"
            :icon="LucideCalendarRange"
            :title="__('No tasks in this project')"
            :message="
              __('Once tasks have due dates, they line up here in order.')
            "
          />

          <template v-else>
            <section
              v-for="group in groups"
              :key="group.key"
              :aria-labelledby="`tl-${group.key}`"
            >
              <h2
                :id="`tl-${group.key}`"
                class="flex items-center gap-2 border-b border-outline-gray-2 bg-surface-gray-1 px-5 py-2 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
              >
                {{ group.label }}
                <span class="font-mono tabular-nums text-ink-gray-5">{{
                  group.tasks.length
                }}</span>
              </h2>
              <ul role="list">
                <li
                  v-for="task in group.tasks"
                  :key="task.name"
                  class="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 border-b border-outline-gray-1 px-5 py-3 last:border-b-0 hover:bg-surface-gray-1 md:grid-cols-[1fr_9rem_8rem_7rem]"
                >
                  <div class="flex min-w-0 items-center gap-2.5">
                    <component
                      :is="priorityIcon(task.priority)"
                      class="size-4 shrink-0"
                      :class="
                        task.priority === 'Urgent'
                          ? 'text-danger'
                          : 'text-ink-gray-5'
                      "
                      role="img"
                      :aria-label="
                        __('{0} priority', __(task.priority || 'Low'))
                      "
                    />
                    <span
                      class="truncate text-[13px] font-medium"
                      :class="
                        isClosed(task)
                          ? 'text-ink-gray-5 line-through'
                          : 'text-ink-gray-9'
                      "
                    >
                      {{ task.subject }}
                    </span>
                  </div>
                  <span
                    class="hidden truncate text-sm text-ink-gray-6 md:block"
                  >
                    {{ task.phase || "—" }}
                  </span>
                  <span class="hidden md:block">
                    <TaskStatusBadge :status="task.status" />
                  </span>
                  <span
                    class="flex items-center justify-end gap-1 text-sm tabular-nums"
                    :class="
                      isOverdue(task)
                        ? 'font-medium text-danger'
                        : 'text-ink-gray-6'
                    "
                  >
                    <LucideAlarmClock
                      v-if="isOverdue(task)"
                      class="size-3.5"
                      aria-hidden="true"
                    />
                    {{
                      task.due_date
                        ? dayjs(task.due_date).format("D MMM YYYY")
                        : "—"
                    }}
                    <span v-if="isOverdue(task)" class="sr-only">{{
                      __("Overdue")
                    }}</span>
                  </span>
                </li>
              </ul>
            </section>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import ProjectNav from "./components/ProjectNav.vue";
import TaskStatusBadge from "./components/TaskStatusBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import {
  isClosed,
  isOverdue,
  loadErrorMessage,
  priorityIcon,
} from "./taskMeta";

const props = defineProps<{ projectId: string }>();

interface Task {
  name: string;
  subject: string;
  phase?: string;
  status: string;
  priority?: string;
  due_date?: string;
}

const tasks = createResource({
  url: "helpdesk.tasky.api.get_project_dashboard",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});
watch(
  () => props.projectId,
  () => {
    if (props.projectId) tasks.reload();
  }
);

const sortedTasks = computed<Task[]>(() => {
  const list: Task[] = tasks.data?.tasks ?? [];
  return [...list].sort((a, b) => {
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
  });
});

const phaseNames = computed(() =>
  sortedTasks.value.map((t) => t.phase || "").filter(Boolean)
);

// group by due month so the list reads as a timeline
const groups = computed(() => {
  const out: { key: string; label: string; tasks: Task[] }[] = [];
  for (const task of sortedTasks.value) {
    const key = task.due_date ? dayjs(task.due_date).format("YYYY-MM") : "none";
    let group = out[out.length - 1];
    if (!group || group.key !== key) {
      group = {
        key,
        label: task.due_date
          ? dayjs(task.due_date).format("MMMM YYYY")
          : __("No due date"),
        tasks: [],
      };
      out.push(group);
    }
    group.tasks.push(task);
  }
  return out;
});
</script>
