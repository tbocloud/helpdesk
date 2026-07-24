<template>
  <div class="flex flex-col gap-4 p-4">
    <div v-if="phases.loading" class="flex items-center justify-center py-12">
      <LoadingIndicator :scale="4" />
    </div>
    <template v-else-if="phases.data">
      <div
        v-for="phase in phases.data"
        :key="phase.name"
        class="border border-outline-gray-2 rounded-lg bg-surface-white overflow-hidden"
      >
        <button
          class="flex items-center justify-between w-full p-4 hover:bg-surface-sidebar transition-colors"
          @click="togglePhase(phase.name)"
        >
          <div class="flex items-center gap-3">
            <component
              :is="expandedPhases.has(phase.name) ? LucideChevronDown : LucideChevronRight"
              class="size-4 text-ink-gray-6 flex-shrink-0"
            />
            <span class="text-base-medium text-ink-gray-9">{{ phase.title || phase.name }}</span>
          </div>
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-2">
              <div class="w-24 h-2 bg-surface-gray-2 rounded-full overflow-hidden">
                <div
                  class="h-full bg-ink-blue-4 rounded-full transition-all"
                  :style="{ width: `${phase.progress || 0}%` }"
                />
              </div>
              <span class="text-sm text-ink-gray-6 whitespace-nowrap">
                {{ phase.completed_count || 0 }}/{{ phase.total_count || 0 }}
              </span>
            </div>
          </div>
        </button>

        <div v-if="expandedPhases.has(phase.name)" class="border-t border-outline-gray-2">
          <div
            v-if="phaseTasks[phase.name]?.loading"
            class="flex items-center justify-center py-6"
          >
            <LoadingIndicator :scale="3" />
          </div>
          <template v-else-if="phaseTasks[phase.name]?.data">
            <div
              v-for="task in phaseTasks[phase.name].data"
              :key="task.name"
              class="flex items-center gap-3 px-4 py-3 hover:bg-surface-sidebar border-b border-outline-gray-2 last:border-b-0 transition-colors"
            >
              <button
                class="flex-shrink-0 size-5 rounded border-2 flex items-center justify-center transition-colors"
                :class="task.completed
                  ? 'bg-ink-blue-4 border-ink-blue-4 text-white'
                  : 'border-outline-gray-3 hover:border-outline-gray-4 text-transparent'"
                @click="onToggleTask(task)"
              >
                <LucideCheck v-if="task.completed" class="size-3" />
              </button>

              <span
                class="flex-1 text-sm truncate"
                :class="task.completed ? 'text-ink-gray-5 line-through' : 'text-ink-gray-8'"
              >
                {{ task.title || task.subject }}
              </span>

              <span
                v-if="task.category"
                class="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
                :class="categoryClasses(task.category)"
              >
                {{ task.category }}
              </span>

              <div v-if="task.assignee || task.assigned_to" class="flex-shrink-0">
                <UserAvatar
                  :name="task.assignee || task.assigned_to"
                  size="sm"
                  :hide-avatar="false"
                />
              </div>

              <span
                class="flex-shrink-0 size-1.5 rounded-full"
                :class="priorityDotClass(task.priority)"
              />

              <span
                class="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
                :class="statusPillClasses(task.status)"
              >
                {{ task.status }}
              </span>

              <div
                v-if="task.overdue"
                class="flex-shrink-0"
                :title="'Overdue'"
              >
                <LucideAlertTriangle class="size-3.5 text-ink-red-5" />
              </div>
              <div
                v-else-if="task.due_date || task.due"
                class="flex-shrink-0 flex items-center gap-1 text-xs text-ink-gray-5"
              >
                <LucideClock class="size-3" />
                <span>{{ task.due_date || task.due }}</span>
              </div>
            </div>
          </template>
          <div
            v-else
            class="flex items-center justify-center py-8 text-sm text-ink-gray-5"
          >
            No tasks in this phase
          </div>
        </div>
      </div>
    </template>
    <div
      v-else
      class="flex items-center justify-center py-12 text-sm text-ink-gray-5"
    >
      No phases found
    </div>
  </div>
</template>

<script setup lang="ts">
import { createResource } from "frappe-ui";
import { reactive, ref, watch } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCheck from "~icons/lucide/check";
import LucideClock from "~icons/lucide/clock";
import LucideAlertTriangle from "~icons/lucide/alert-triangle";
import { UserAvatar } from "@/components";

const props = defineProps<{
  projectId: string;
}>();

const expandedPhases = reactive<Set<string>>(new Set());

const phases = createResource({
  url: "helpdesk.tasky.api.get_project_dashboard",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
});

const phaseTasks: Record<string, ReturnType<typeof createResource>> = reactive({});

const updateTaskStatus = createResource({
  url: "helpdesk.tasky.api.update_task_status",
});

function togglePhase(phaseName: string) {
  if (expandedPhases.has(phaseName)) {
    expandedPhases.delete(phaseName);
  } else {
    expandedPhases.add(phaseName);
    if (!phaseTasks[phaseName]) {
      phaseTasks[phaseName] = createResource({
        url: "helpdesk.tasky.api.get_phase_tasks",
        params: { phase: phaseName },
        auto: true,
      });
    }
  }
}

function onToggleTask(task: Record<string, any>) {
  const completed = !task.completed;
  task.completed = completed;
  updateTaskStatus.submit({ task: task.name, completed });
}

function categoryClasses(category: string) {
  const map: Record<string, string> = {
    Functional: "bg-ink-blue-1 text-ink-blue-8",
    Development: "bg-ink-purple-1 text-ink-purple-8",
    Support: "bg-ink-green-1 text-ink-green-8",
    Common: "bg-ink-gray-2 text-ink-gray-7",
  };
  return map[category] || map.Common;
}

function priorityDotClass(priority: string) {
  const map: Record<string, string> = {
    Urgent: "bg-ink-red-5",
    High: "bg-ink-amber-5",
    Medium: "bg-ink-blue-4",
    Low: "bg-ink-gray-4",
  };
  return map[priority] || map.Low;
}

function statusPillClasses(status: string) {
  const map: Record<string, string> = {
    Open: "bg-ink-gray-2 text-ink-gray-7",
    Working: "bg-ink-amber-1 text-ink-amber-8",
    "Pending Review": "bg-ink-purple-1 text-ink-purple-8",
    Completed: "bg-ink-green-1 text-ink-green-8",
    Cancelled: "bg-ink-gray-2 text-ink-gray-5 line-through",
  };
  return map[status] || map.Open;
}
</script>
