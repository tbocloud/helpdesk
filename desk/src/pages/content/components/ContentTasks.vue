<template>
  <div class="flex flex-col gap-4">
    <!-- loading: the columns' shape, so nothing jumps when the cards arrive -->
    <div
      v-if="loading && !data"
      class="grid grid-cols-1 gap-4 lg:grid-cols-4"
      :aria-label="__('Loading tasks')"
      aria-busy="true"
    >
      <div v-for="i in 4" :key="i" class="flex flex-col gap-2">
        <div class="h-5 w-28 animate-pulse rounded bg-surface-gray-2" />
        <div
          v-for="j in 2"
          :key="j"
          class="h-36 animate-pulse rounded-xl bg-surface-gray-2"
        />
      </div>
    </div>

    <TaskyState
      v-else-if="error && !data"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the tasks')"
      :message="errorText(error, __('Check your connection and try again.'))"
    >
      <Button :label="__('Try again')" @click="emit('retry')" />
    </TaskyState>

    <template v-else-if="data">
      <TaskyState
        v-if="!data.tasks.length"
        :icon="LucideClipboardCheck"
        :title="
          person === auth.userId
            ? __('Nothing on your plate')
            : __('No content tasks {0}', periodText)
        "
        :message="
          person === auth.userId
            ? __('No content tasks for you {0}.', periodText)
            : __(
                'Tasks show here once the posts going live {0} have people on them.',
                periodText
              )
        "
      >
        <Button
          v-if="person === auth.userId && data.sees_all"
          :label="__('Show everyone\'s tasks')"
          @click="emit('show-everyone')"
        />
      </TaskyState>

      <TaskyState
        v-else-if="!shown.length"
        :icon="LucideSearchX"
        :title="
          person === auth.userId
            ? __('Nothing on your plate')
            : __('No tasks match these filters')
        "
        :message="
          person === auth.userId
            ? __('No content tasks for you {0}.', periodText)
            : __('No content tasks for {0} {1}.', personName, periodText)
        "
      >
        <Button
          v-if="person === auth.userId && data.sees_all"
          :label="__('Show everyone\'s tasks')"
          @click="emit('show-everyone')"
        />
        <Button
          v-else
          :label="__('Clear filters')"
          @click="emit('clear-filters')"
        />
      </TaskyState>

      <template v-else>
        <p
          v-if="!openCount"
          class="flex items-center gap-2 rounded-xl border border-dashed border-outline-gray-3 px-3 py-2 text-sm text-ink-gray-7"
          role="status"
        >
          <LucideCircleCheck
            class="size-4 shrink-0 text-success"
            aria-hidden="true"
          />
          {{
            person === auth.userId
              ? __("Nothing on your plate: everything {0} is done.", periodText)
              : __("Everything {0} is done.", periodText)
          }}
        </p>

        <!-- on phones one stage at a time, picked here; side by side from lg -->
        <div v-if="openCount" class="-mx-1 overflow-x-auto px-1 lg:hidden">
          <TabButtons
            v-model="phoneStage"
            size="md"
            :aria-label="__('Stage')"
            :options="
              openColumns.map((c) => ({
                label: c.label,
                value: c.key,
                iconLeft: c.icon,
              }))
            "
          >
            <template #suffix="{ button, checked }">
              <span
                class="font-mono text-xs tabular-nums"
                :class="checked ? '' : 'text-ink-gray-5'"
                >{{ countOf(button.modelValue) }}</span
              >
            </template>
          </TabButtons>
        </div>

        <div
          v-if="openCount"
          class="grid grid-cols-1 items-start gap-4 lg:grid-cols-4"
        >
          <section
            v-for="column in openColumns"
            :key="column.key"
            class="min-w-0 flex-col gap-2"
            :class="column.key === phoneStage ? 'flex' : 'hidden lg:flex'"
            :aria-labelledby="`stage-${column.key}`"
          >
            <h2
              :id="`stage-${column.key}`"
              class="flex items-center gap-2 px-0.5 text-sm font-medium text-ink-gray-7 max-lg:sr-only"
            >
              <component
                :is="column.icon"
                class="size-4 text-ink-gray-5"
                aria-hidden="true"
              />
              {{ column.label }}
              <span
                class="grid h-5 min-w-[1.25rem] place-items-center rounded-full bg-surface-gray-2 px-1.5 font-mono text-xs tabular-nums text-ink-gray-7"
                >{{ column.tasks.length }}</span
              >
            </h2>
            <p
              v-if="!column.tasks.length"
              class="rounded-xl border border-dashed border-outline-gray-2 px-3 py-4 text-center text-sm text-ink-gray-5"
            >
              {{ column.empty }}
            </p>
            <ul v-else class="flex flex-col gap-2">
              <li v-for="task in column.tasks" :key="task.name">
                <ContentTaskCard
                  :task="task"
                  :post="data.posts[task.post]"
                  :now="now"
                  :busy="busy === task.name"
                  @open="open(task)"
                  @view-post="emit('open-post', task.post)"
                  @step="onStep($event, task)"
                />
              </li>
            </ul>
          </section>
        </div>

        <!-- done work folds away; it's there for a look back -->
        <section
          v-if="done.length"
          class="flex flex-col gap-2"
          aria-labelledby="stage-done"
        >
          <div
            class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-1.5 text-sm"
          >
            <LucideCircleCheck
              class="size-4 shrink-0 text-success"
              aria-hidden="true"
            />
            <h2 id="stage-done" class="min-w-0 flex-1 text-ink-gray-7">
              <span class="font-medium text-ink-gray-9">{{
                __("Done {0}", periodText)
              }}</span>
              ·
              <span class="font-mono tabular-nums">{{ done.length }}</span>
              {{ done.length === 1 ? __("task") : __("tasks") }}
            </h2>
            <button
              type="button"
              class="relative inline-flex h-8 items-center rounded-[10px] border border-outline-gray-2 bg-surface-base px-3 text-sm font-medium text-ink-gray-8 transition-colors after:absolute after:-inset-1.5 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              :aria-expanded="showDone"
              @click="showDone = !showDone"
            >
              {{ showDone ? __("Hide") : __("Show") }}
            </button>
          </div>
          <ul
            v-if="showDone"
            class="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4"
          >
            <li v-for="task in done" :key="task.name">
              <ContentTaskCard
                :task="task"
                :post="data.posts[task.post]"
                :now="now"
                :busy="busy === task.name"
                @open="open(task)"
                @view-post="emit('open-post', task.post)"
                @step="onStep($event, task)"
              />
            </li>
          </ul>
        </section>
      </template>

      <p v-if="data.truncated" class="text-p-sm text-ink-gray-5">
        {{
          __(
            "Showing the first 1,000 tasks. Narrow the filters to see the rest."
          )
        }}
      </p>
    </template>

    <TaskDetailDialog
      v-model:task="dialogTask"
      :action="dialogAction"
      :mine="dialogMine"
      @changed="emit('changed')"
    />
  </div>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import { taskStatusMeta } from "@/pages/tasky/taskMeta";
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import { Button, dayjs, TabButtons } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideSearchX from "~icons/lucide/search-x";
import type { ContentPost, TeamRole } from "../constants";
import {
  type ContentTask,
  type ContentTasksData,
  type TaskStage,
  type TaskStep,
  useContentTaskSteps,
} from "../contentTasks";
import ContentTaskCard from "./ContentTaskCard.vue";

const props = defineProps<{
  data?: ContentTasksData | null;
  loading?: boolean;
  error?: unknown;
  /** The page's person filter: only the tasks assigned to them. */
  person?: string;
  /** "this month", "this week", "on Mon 12 Oct". */
  periodText: string;
  /** The period on screen; Done folds again when it changes. */
  periodKey: string;
}>();

const emit = defineEmits<{
  "open-post": [name: string];
  reassign: [post: ContentPost, role: TeamRole];
  changed: [];
  retry: [];
  "clear-filters": [];
  "show-everyone": [];
}>();

const auth = useAuthStore();
const userStore = useUserStore();

const personName = computed(() => {
  if (!props.person) return "";
  return userStore.getUser(props.person)?.full_name || props.person;
});

const shown = computed(() =>
  (props.data?.tasks ?? []).filter(
    (t) => !props.person || t.assignees.includes(props.person)
  )
);

// labels and icons from the task statuses each column holds
const COLUMNS: {
  key: TaskStage;
  status: string;
  label: string;
  empty: string;
}[] = [
  {
    key: "todo",
    status: "Open",
    label: __("To do"),
    empty: __("Nothing waiting to start"),
  },
  {
    key: "in_progress",
    status: "Working",
    label: __("In progress"),
    empty: __("Nothing in progress"),
  },
  {
    key: "review",
    status: "Pending Review",
    label: __("In review"),
    empty: __("Nothing waiting on a review"),
  },
  {
    key: "on_hold",
    status: "On Hold",
    label: __("On hold"),
    empty: __("Nothing on hold"),
  },
];

const openColumns = computed(() =>
  COLUMNS.map((c) => ({
    ...c,
    icon: taskStatusMeta(c.status).icon,
    tasks: shown.value.filter((t) => t.stage === c.key),
  }))
);
const openCount = computed(
  () => shown.value.filter((t) => t.stage !== "done").length
);
const done = computed(() => shown.value.filter((t) => t.stage === "done"));

function countOf(stage: TaskStage) {
  return openColumns.value.find((c) => c.key === stage)?.tasks.length ?? 0;
}
// the stage a phone shows: the one picked, else the first with work in it
const pickedStage = ref<TaskStage | null>(null);
const phoneStage = computed<TaskStage>({
  get: () =>
    pickedStage.value ??
    openColumns.value.find((c) => c.tasks.length)?.key ??
    "todo",
  set: (stage) => (pickedStage.value = stage),
});

const showDone = ref(false);
watch(
  () => props.periodKey,
  () => (showDone.value = false)
);

// timers read the clock; a list refreshes by the minute, not the second
const now = ref(dayjs());
useIntervalFn(() => (now.value = dayjs()), 30_000);

const {
  busy,
  dialogTask,
  dialogAction,
  dialogMine,
  open: openDialog,
  run,
} = useContentTaskSteps(() => emit("changed"));

function open(task: ContentTask) {
  openDialog(
    {
      name: task.name,
      subject: task.subject,
      project: task.project,
      project_name: task.project_name,
    },
    task.mine
  );
}

function onStep(step: TaskStep, task: ContentTask) {
  if (step !== "reassign") return run(step, task);
  const post = props.data?.posts[task.post];
  if (post && task.role) emit("reassign", post, task.role);
}
</script>
