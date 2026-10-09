<template>
  <div class="flex h-full flex-col">
    <ProjectNav
      ref="nav"
      :project-id="projectId"
      :phases="phaseNames"
      @task-created="reloadAll"
    >
      <template #actions>
        <Button
          v-if="canManage"
          class="min-h-11 min-w-11 md:min-h-0 md:min-w-0"
          :label="__('Generate checklist')"
          @click="showChecklistModal = true"
        >
          <template #prefix
            ><LucideClipboardList class="size-4" aria-hidden="true"
          /></template>
          <span class="hidden md:inline">{{ __("Generate checklist") }}</span>
        </Button>
      </template>
    </ProjectNav>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="phases.error && !phases.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the checklist')"
          :message="loadErrorMessage(phases.error)"
        >
          <Button :label="__('Retry')" @click="phases.reload()" />
        </TaskyState>

        <!-- Loading -->
        <div
          v-else-if="!phases.data"
          class="flex flex-col gap-3"
          aria-busy="true"
        >
          <div
            v-for="i in 4"
            :key="i"
            class="flex items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <div class="size-4 animate-pulse rounded bg-surface-gray-2" />
            <div class="h-4 w-1/3 animate-pulse rounded bg-surface-gray-2" />
            <div
              class="ml-auto h-1.5 w-24 animate-pulse rounded-full bg-surface-gray-2"
            />
          </div>
        </div>

        <!-- Empty -->
        <div
          v-else-if="!phaseList.length && !unphasedTasks.length"
          class="rounded-xl border border-outline-gray-2 bg-surface-base"
        >
          <TaskyState
            :icon="LucideListChecks"
            :title="__('No tasks yet')"
            :message="
              canManage
                ? __(
                    'Generate a checklist from a template, or add tasks one at a time.'
                  )
                : canAddTasks
                ? __('Add a task, or wait for tasks assigned to you.')
                : __('Tasks assigned to you in this project will show up here.')
            "
          >
            <template v-if="canAddTasks">
              <Button
                v-if="canManage"
                :label="__('Generate checklist')"
                @click="showChecklistModal = true"
              />
              <Button
                variant="solid"
                :label="__('New task')"
                @click="nav?.openNewTask()"
              >
                <template #prefix
                  ><LucidePlus class="size-4" aria-hidden="true"
                /></template>
              </Button>
            </template>
          </TaskyState>
        </div>

        <template v-else>
          <!-- Summary -->
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div class="text-sm text-ink-gray-6">
              <span class="font-mono tabular-nums text-ink-gray-9">{{
                stats.completed ?? 0
              }}</span>
              {{ __("of") }}
              <span class="font-mono tabular-nums text-ink-gray-9">{{
                stats.total ?? 0
              }}</span>
              {{ __("tasks completed") }}
              <template v-if="stats.overdue">
                <span aria-hidden="true">·</span>
                <span
                  class="inline-flex items-center gap-1 font-medium text-danger"
                >
                  <LucideAlarmClock class="size-3.5" aria-hidden="true" />
                  <span class="tabular-nums">{{ stats.overdue }}</span>
                  {{ __("overdue") }}
                </span>
              </template>
              <template v-if="stats.on_hold">
                <span aria-hidden="true">·</span>
                <span
                  class="inline-flex items-center gap-1 font-medium text-warning"
                >
                  <LucidePause class="size-3.5" aria-hidden="true" />
                  <span class="tabular-nums">{{ stats.on_hold }}</span>
                  {{ __("on hold") }}
                </span>
              </template>
            </div>
            <div class="flex items-center gap-2">
              <div
                class="h-1.5 w-40 overflow-hidden rounded-full bg-surface-gray-2"
                role="progressbar"
                :aria-valuenow="stats.completion_pct ?? 0"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-label="__('Project progress')"
              >
                <div
                  class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-500"
                  :style="{ width: `${stats.completion_pct ?? 0}%` }"
                />
              </div>
              <span
                class="w-12 text-right font-mono text-xs tabular-nums text-ink-gray-6"
              >
                {{ stats.completion_pct ?? 0 }}%
              </span>
            </div>
          </div>

          <div class="flex flex-col gap-3">
            <section
              v-for="phase in phaseList"
              :key="phase.name"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
            >
              <h2>
                <button
                  type="button"
                  class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none"
                  :aria-expanded="expandedPhases.has(phase.phase_name)"
                  :aria-controls="`phase-${phase.name}`"
                  @click="togglePhase(phase.phase_name)"
                >
                  <component
                    :is="
                      expandedPhases.has(phase.phase_name)
                        ? LucideChevronDown
                        : LucideChevronRight
                    "
                    class="size-4 shrink-0 text-ink-gray-5"
                    aria-hidden="true"
                  />
                  <span
                    class="min-w-0 flex-1 truncate text-base-medium text-ink-gray-9"
                  >
                    {{ phase.phase_name || phase.name }}
                  </span>
                  <LucideCircleCheck
                    v-if="
                      phase.total_count &&
                      phase.completed_count === phase.total_count
                    "
                    class="size-4 shrink-0 text-success"
                    :aria-label="__('Phase complete')"
                    role="img"
                  />
                  <div
                    class="hidden h-1.5 w-24 overflow-hidden rounded-full bg-surface-gray-2 sm:block"
                    aria-hidden="true"
                  >
                    <div
                      class="h-full rounded-full bg-surface-gray-7 transition-[width] duration-500"
                      :style="{ width: `${phase.progress_pct || 0}%` }"
                    />
                  </div>
                  <span
                    class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-ink-gray-6"
                  >
                    {{ phase.completed_count || 0 }}/{{
                      phase.total_count || 0
                    }}
                  </span>
                </button>
              </h2>

              <div
                v-if="expandedPhases.has(phase.phase_name)"
                :id="`phase-${phase.name}`"
                class="border-t border-outline-gray-2"
              >
                <div
                  v-if="
                    phaseTasks[phase.phase_name]?.loading &&
                    !phaseTasks[phase.phase_name]?.data
                  "
                >
                  <div
                    v-for="i in 3"
                    :key="i"
                    class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                  >
                    <div
                      class="size-4 animate-pulse rounded bg-surface-gray-2"
                    />
                    <div
                      class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                    />
                  </div>
                </div>
                <div
                  v-else-if="phaseTasks[phase.phase_name]?.error"
                  class="flex items-center justify-between gap-3 px-4 py-3 text-p-sm text-ink-gray-6"
                  role="alert"
                >
                  {{ __("Couldn't load tasks in this phase.") }}
                  <Button
                    :label="__('Retry')"
                    @click="phaseTasks[phase.phase_name].reload()"
                  />
                </div>
                <ul
                  v-else-if="phaseTasks[phase.phase_name]?.data?.length"
                  role="list"
                >
                  <li
                    v-for="task in phaseTasks[phase.phase_name].data"
                    :key="task.name"
                    class="border-b border-outline-gray-1 last:border-b-0"
                  >
                    <ChecklistRow
                      :task="task"
                      :can-manage="canManage"
                      :can-edit="canEdit(task)"
                      @toggle="onToggleTask(task)"
                      @hold="holdingTask = task"
                      @resume="resumingTask = task"
                      @plan="planningTask = task"
                      @edit="editingTask = task"
                      @approve="approve(task)"
                      @send-back="sendingBackTask = task"
                      @ask-help="helpingTask = task"
                      @hand-over="handingOverTask = task"
                    />
                  </li>
                </ul>
                <p
                  v-else
                  class="px-4 py-6 text-center text-p-sm text-ink-gray-5"
                >
                  {{ __("No tasks in this phase") }}
                </p>
              </div>
            </section>

            <section
              v-if="unphasedTasks.length"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
            >
              <h2 class="flex items-center gap-3 px-4 py-3">
                <LucideInbox
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                <span class="flex-1 text-base-medium text-ink-gray-9">{{
                  __("No phase")
                }}</span>
                <span class="font-mono text-xs tabular-nums text-ink-gray-6">
                  {{
                    unphasedTasks.filter((t) => t.status === "Completed")
                      .length
                  }}/{{ unphasedTasks.length }}
                </span>
              </h2>
              <ul role="list" class="border-t border-outline-gray-2">
                <li
                  v-for="task in unphasedTasks"
                  :key="task.name"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <ChecklistRow
                    :task="task"
                    :can-manage="canManage"
                    :can-edit="canEdit(task)"
                    @toggle="onToggleTask(task)"
                    @hold="holdingTask = task"
                    @resume="resumingTask = task"
                    @plan="planningTask = task"
                    @edit="editingTask = task"
                    @approve="approve(task)"
                    @send-back="sendingBackTask = task"
                    @ask-help="helpingTask = task"
                    @hand-over="handingOverTask = task"
                  />
                </li>
              </ul>
            </section>
          </div>
        </template>
      </div>
    </div>

    <CompleteTaskDialog v-model:task="completingTask" @completed="reloadAll" />

    <HoldTaskDialog v-model:task="holdingTask" @held="reloadAll" />
    <ResumeTaskDialog v-model:task="resumingTask" @resumed="reloadAll" />
    <RequestHelpDialog
      v-model:task="helpingTask"
      :project-id="projectId"
      @requested="reloadAll"
    />
    <HandOverTaskDialog
      v-model:task="handingOverTask"
      :project-id="projectId"
      @handed-over="reloadAll"
    />
    <EditTaskDialog
      v-model:task="editingTask"
      :project-id="projectId"
      :phases="phaseNames"
      @saved="reloadAll"
      @plan="(t) => (planningTask = t)"
    />
    <TaskPlanDialog
      v-model:task="planningTask"
      :project-id="projectId"
      @saved="reloadAll"
    />
    <SendBackTaskDialog v-model:task="sendingBackTask" @sent="reloadAll" />

    <GenerateChecklistModal
      v-if="showChecklistModal"
      :show="showChecklistModal"
      :project-id="projectId"
      @close="showChecklistModal = false"
      @generated="onChecklistGenerated"
      @add-task="onChecklistAddTask"
    />
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { useAuthStore } from "@/stores/auth";
import { loadErrorMessage } from "./taskMeta";
import { __ } from "@/translation";
import { Button, createResource, toast } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideInbox from "~icons/lucide/inbox";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePause from "~icons/lucide/pause";
import LucidePlus from "~icons/lucide/plus";
import ChecklistRow from "./components/ChecklistRow.vue";
import CompleteTaskDialog from "./components/CompleteTaskDialog.vue";
import EditTaskDialog from "./components/EditTaskDialog.vue";
import GenerateChecklistModal from "./components/GenerateChecklistModal.vue";
import HandOverTaskDialog from "./components/HandOverTaskDialog.vue";
import HoldTaskDialog from "./components/HoldTaskDialog.vue";
import ProjectNav from "./components/ProjectNav.vue";
import RequestHelpDialog from "./components/RequestHelpDialog.vue";
import ResumeTaskDialog from "./components/ResumeTaskDialog.vue";
import SendBackTaskDialog from "./components/SendBackTaskDialog.vue";
import TaskPlanDialog from "./components/TaskPlanDialog.vue";
import TaskyState from "@/components/TaskyState.vue";
import { blockedMessage, blocksMove, isPendingReview } from "./taskMeta";
import { useApproveTask } from "./useApproveTask";

const props = defineProps<{ projectId: string }>();

interface Phase {
  name: string;
  phase_name: string;
  total_count: number;
  completed_count: number;
  progress_pct: number;
}

const nav = ref<InstanceType<typeof ProjectNav> | null>(null);
const expandedPhases = reactive<Set<string>>(new Set());
const phaseTasks: Record<string, ReturnType<typeof createResource>> = reactive(
  {}
);
const showChecklistModal = ref(false);

const phases = createResource({
  url: "helpdesk.tasky.api.get_project_dashboard",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});

const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});

watch(
  () => props.projectId,
  (id, prev) => {
    if (!id || !prev) return;
    expandedPhases.clear();
    for (const key of Object.keys(phaseTasks)) delete phaseTasks[key];
    phases.reload();
    projectDetail.reload();
  }
);

const canManage = computed(() => !!projectDetail.data?.can_manage);
const canAddTasks = computed(() => !!projectDetail.data?.can_add_tasks);
const authStore = useAuthStore();

// the assignee may edit the description; leads and managers everything
function canEdit(task: Record<string, any>) {
  return canManage.value || !!task.assignees?.includes(authStore.userId);
}
const phaseList = computed<Phase[]>(() => phases.data?.phases ?? []);
const phaseNames = computed(() => phaseList.value.map((p) => p.phase_name));
const stats = computed(() => phases.data?.stats ?? {});
// the dashboard's phase summary skips tasks without a phase; list those separately
const unphasedTasks = computed<Record<string, any>[]>(() =>
  (phases.data?.tasks ?? []).filter((t: Record<string, any>) => !t.phase)
);

function reloadAll() {
  phases.reload();
  Object.values(phaseTasks).forEach((r) => r.reload());
}

const updateTaskStatus = createResource({
  url: "helpdesk.tasky.api.update_task_status",
  onSuccess() {
    phases.reload();
  },
  onError(e: any) {
    toast.error(errorText(e, __("Couldn't reopen the task.")));
    reloadAll();
  },
});

const holdingTask = ref<Record<string, any> | null>(null);
const resumingTask = ref<Record<string, any> | null>(null);
const planningTask = ref<Record<string, any> | null>(null);
const editingTask = ref<Record<string, any> | null>(null);
const sendingBackTask = ref<Record<string, any> | null>(null);
const helpingTask = ref<Record<string, any> | null>(null);
const handingOverTask = ref<Record<string, any> | null>(null);

const { approve } = useApproveTask(reloadAll);

const completingTask = ref<Record<string, any> | null>(null);

function togglePhase(phaseName: string) {
  if (expandedPhases.has(phaseName)) {
    expandedPhases.delete(phaseName);
    return;
  }
  expandedPhases.add(phaseName);
  if (!phaseTasks[phaseName]) {
    phaseTasks[phaseName] = createResource({
      url: "helpdesk.tasky.api.get_phase_tasks",
      makeParams: () => ({ project: props.projectId, phase: phaseName }),
      auto: true,
      onError() {},
    });
  }
}

function onToggleTask(task: Record<string, any>) {
  if (task.status === "Completed") {
    updateTaskStatus.submit({ task: task.name, status: "Open" });
    task.status = "Open";
    return;
  }
  if (blocksMove(task, "Completed")) {
    toast.error(blockedMessage(task));
    return;
  }
  // a lead ticking a reviewed task signs it off; anyone else logs their time
  if (isPendingReview(task) && canManage.value) {
    approve(task);
    return;
  }
  completingTask.value = task;
}

function onChecklistGenerated() {
  showChecklistModal.value = false;
  reloadAll();
}

function onChecklistAddTask() {
  showChecklistModal.value = false;
  nav.value?.openNewTask();
}
</script>
