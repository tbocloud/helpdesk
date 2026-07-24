<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Checklist") }}</div>
      </template>
      <template #right-header>
        <div class="flex items-center gap-1">
          <router-link v-for="tab in projectTabs" :key="tab.to" :to="{ name: tab.to, params: { projectId } }"
            class="px-3 py-1.5 rounded text-sm transition-colors"
            :class="route.name === tab.to ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'">
            {{ __(tab.label) }}
          </router-link>
        </div>
      </template>
    </LayoutHeader>
    <div class="flex-1 overflow-auto p-4">
      <div v-if="phases.loading" class="flex items-center justify-center py-12">
        <LoadingIndicator :scale="4" />
      </div>
      <template v-else-if="phases.data?.phases">
        <div v-for="phase in phases.data.phases" :key="phase.name" class="border border-outline-gray-2 rounded-lg bg-surface-white overflow-hidden mb-3">
          <button class="flex items-center justify-between w-full p-4 hover:bg-surface-sidebar transition-colors" @click="togglePhase(phase.phase_name)">
            <div class="flex items-center gap-3">
              <component :is="expandedPhases.has(phase.phase_name) ? LucideChevronDown : LucideChevronRight" class="size-4 text-ink-gray-6 flex-shrink-0" />
              <span class="text-base-medium text-ink-gray-9">{{ phase.phase_name || phase.name }}</span>
            </div>
            <div class="flex items-center gap-3">
              <div class="flex items-center gap-2">
                <div class="w-24 h-2 bg-surface-gray-2 rounded-full overflow-hidden">
                  <div class="h-full bg-ink-blue-4 rounded-full transition-all" :style="{ width: `${phase.progress_pct || 0}%` }" />
                </div>
                <span class="text-sm text-ink-gray-6 whitespace-nowrap">{{ phase.completed_count || 0 }}/{{ phase.total_count || 0 }}</span>
              </div>
            </div>
          </button>
          <div v-if="expandedPhases.has(phase.phase_name)" class="border-t border-outline-gray-2">
            <div v-if="phaseTasks[phase.phase_name]?.loading" class="flex items-center justify-center py-6"><LoadingIndicator :scale="3" /></div>
            <template v-else-if="phaseTasks[phase.phase_name]?.data">
              <div v-for="task in phaseTasks[phase.phase_name].data" :key="task.name" class="flex items-center gap-3 px-4 py-3 hover:bg-surface-sidebar border-b border-outline-gray-2 last:border-b-0">
                <button class="flex-shrink-0 size-5 rounded border-2 flex items-center justify-center transition-colors"
                  :class="task.status === 'Completed' ? 'bg-ink-blue-4 border-ink-blue-4 text-white' : 'border-outline-gray-3 hover:border-outline-gray-4 text-transparent'"
                  @click="onToggleTask(task)">
                  <LucideCheck v-if="task.status === 'Completed'" class="size-3" />
                </button>
                <span class="flex-1 text-sm truncate" :class="task.status === 'Completed' ? 'text-ink-gray-5 line-through' : 'text-ink-gray-8'">{{ task.subject }}</span>
                <span v-if="task.category" class="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap" :class="categoryClasses(task.category)">{{ task.category }}</span>
                <div v-if="task.assigned_to" class="flex-shrink-0"><UserAvatar :name="task.assigned_to" size="sm" :hide-avatar="false" /></div>
                <span class="flex-shrink-0 size-1.5 rounded-full" :class="priorityDotClass(task.priority)" />
                <span class="text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap" :class="statusPillClasses(task.status)">{{ task.status }}</span>
              </div>
            </template>
            <div v-else class="flex items-center justify-center py-8 text-sm text-ink-gray-5">{{ __("No tasks in this phase") }}</div>
          </div>
        </div>
      </template>
      <div v-else class="flex items-center justify-center py-12 text-sm text-ink-gray-5">{{ __("No phases found") }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { createResource } from "frappe-ui";
import { reactive } from "vue";
import { useRoute } from "vue-router";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { UserAvatar } from "@/components";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCheck from "~icons/lucide/check";

const props = defineProps<{ projectId: string }>();
const route = useRoute();

const projectTabs = [
  { label: "Dashboard", to: "TaskyProject" },
  { label: "Checklist", to: "TaskyChecklist" },
  { label: "Board", to: "TaskyKanban" },
  { label: "Timeline", to: "TaskyTimeline" },
  { label: "Overdue", to: "TaskyOverdue" },
];

const expandedPhases = reactive<Set<string>>(new Set());
const phaseTasks: Record<string, ReturnType<typeof createResource>> = reactive({});

const phases = createResource({ url: "helpdesk.tasky.api.get_project_dashboard", makeParams: () => ({ project: props.projectId }), auto: true });

const updateTaskStatus = createResource({ url: "helpdesk.tasky.api.update_task_status" });

function togglePhase(phaseName: string) {
  if (expandedPhases.has(phaseName)) { expandedPhases.delete(phaseName); return; }
  expandedPhases.add(phaseName);
  if (!phaseTasks[phaseName]) {
    phaseTasks[phaseName] = createResource({ url: "helpdesk.tasky.api.get_phase_tasks", makeParams: () => ({ project: props.projectId, phase: phaseName }), auto: true });
  }
}

function onToggleTask(task: Record<string, any>) {
  const newStatus = task.status === "Completed" ? "Open" : "Completed";
  task.status = newStatus;
  updateTaskStatus.submit({ task: task.name, status: newStatus });
}

function categoryClasses(c: string) {
  const m: Record<string, string> = { Functional: "bg-ink-blue-1 text-ink-blue-8", Development: "bg-ink-purple-1 text-ink-purple-8", Support: "bg-ink-green-1 text-ink-green-8", Common: "bg-ink-gray-2 text-ink-gray-7" };
  return m[c] || m.Common;
}
function priorityDotClass(p: string) {
  const m: Record<string, string> = { Urgent: "bg-ink-red-5", High: "bg-ink-amber-5", Medium: "bg-ink-blue-4", Low: "bg-ink-gray-4" };
  return m[p] || m.Low;
}
function statusPillClasses(s: string) {
  const m: Record<string, string> = { Open: "bg-ink-gray-2 text-ink-gray-7", Working: "bg-ink-amber-1 text-ink-amber-8", "Pending Review": "bg-ink-blue-1 text-ink-blue-8", Completed: "bg-ink-green-1 text-ink-green-8", Cancelled: "bg-ink-gray-2 text-ink-gray-5 line-through" };
  return m[s] || m.Open;
}
</script>
