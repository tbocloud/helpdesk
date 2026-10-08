<template>
  <article
    class="flex min-w-0 flex-col rounded-lg border border-outline-gray-2 bg-surface-base transition-colors hover:border-outline-gray-3"
    :aria-labelledby="headingId"
  >
    <div class="flex flex-1 flex-col gap-4 p-4">
      <!-- Name, then who it's for -->
      <header class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h3 :id="headingId" class="text-base-semibold text-ink-gray-9">
            <RouterLink
              :to="{
                name: 'TaskyProject',
                params: { projectId: project.name },
              }"
              class="block truncate rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :title="project.project_name || project.name"
            >
              {{ project.project_name || project.name }}
            </RouterLink>
          </h3>
          <p
            class="mt-0.5 flex min-w-0 items-center gap-1.5 text-sm text-ink-gray-6"
          >
            <span v-if="project.customer" class="truncate">
              {{ project.customer }}
            </span>
            <span v-if="project.customer" aria-hidden="true">·</span>
            <span class="shrink-0 font-mono text-xs text-ink-gray-5">
              {{ project.name }}
            </span>
          </p>
        </div>
        <TaskStatusBadge
          v-if="project.status && project.status !== 'Open'"
          kind="project"
          :status="project.status"
        />
      </header>

      <!-- Lead and dates -->
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
        <dt class="text-ink-gray-5">{{ __("Lead") }}</dt>
        <dd class="truncate text-ink-gray-8">
          {{ project.project_lead_name || project.project_lead || __("None") }}
        </dd>
        <dt class="text-ink-gray-5">{{ __("Dates") }}</dt>
        <dd class="flex min-w-0 flex-wrap items-center gap-x-2 tabular-nums">
          <span class="text-ink-gray-8">{{ dateRange }}</span>
          <span
            v-if="endNote"
            class="inline-flex items-center gap-1"
            :class="
              endNote.late ? 'font-medium text-danger' : 'text-ink-gray-5'
            "
          >
            <LucideAlarmClock
              v-if="endNote.late"
              class="size-3.5"
              aria-hidden="true"
            />
            {{ endNote.text }}
          </span>
        </dd>
      </dl>

      <!-- Progress -->
      <div
        v-if="loading"
        class="flex flex-col gap-2"
        :aria-label="__('Loading')"
      >
        <div class="h-3 w-1/3 animate-pulse rounded bg-surface-gray-2" />
        <div
          class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-2"
        />
      </div>
      <p v-else-if="failed" class="text-p-sm text-ink-gray-5">
        {{ __("Task progress didn't load. Refresh to try again.") }}
      </p>
      <div v-else-if="stats && stats.total" class="flex flex-col gap-2">
        <div class="flex items-baseline justify-between gap-2 text-sm">
          <span class="text-ink-gray-6">{{ __("Tasks done") }}</span>
          <span class="font-mono tabular-nums text-ink-gray-8">
            {{ stats.completed }}/{{ stats.total }}
            <span class="text-ink-gray-5">· {{ stats.completion_pct }}%</span>
          </span>
        </div>
        <div
          class="h-1.5 w-full overflow-hidden rounded-full"
          :class="TRACK[barTone]"
          role="meter"
          :aria-valuenow="stats.completion_pct"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="
            __(
              '{0} of {1} tasks completed',
              String(stats.completed),
              String(stats.total)
            )
          "
        >
          <div
            class="h-full rounded-full"
            :class="FILL[barTone]"
            :style="{ width: `${Math.min(stats.completion_pct, 100)}%` }"
          />
        </div>
        <p
          class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs tabular-nums text-ink-gray-6"
        >
          <span
            v-if="stats.overdue"
            class="inline-flex items-center gap-1 font-medium text-danger"
          >
            <LucideAlarmClock class="size-3.5" aria-hidden="true" />
            {{ __("{0} overdue", String(stats.overdue)) }}
          </span>
          <span v-if="stats.in_progress">
            {{ __("{0} in progress", String(stats.in_progress)) }}
          </span>
          <span v-if="stats.reviewing">
            {{ __("{0} in review", String(stats.reviewing)) }}
          </span>
          <span v-if="stats.on_hold">
            {{ __("{0} on hold", String(stats.on_hold)) }}
          </span>
        </p>
      </div>
      <p v-else-if="stats" class="text-p-sm text-ink-gray-5">
        {{ __("No tasks yet.") }}
      </p>

      <!-- Phases -->
      <div v-if="phases.length">
        <button
          type="button"
          class="flex items-center gap-1 rounded text-xs text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :aria-expanded="showPhases"
          :aria-controls="phasesId"
          @click="showPhases = !showPhases"
        >
          <component
            :is="showPhases ? LucideChevronDown : LucideChevronRight"
            class="size-3.5"
            aria-hidden="true"
          />
          {{ __("Phases") }}
          <span class="font-mono tabular-nums text-ink-gray-5">
            {{ phases.length }}
          </span>
        </button>
        <ul
          v-if="showPhases"
          :id="phasesId"
          role="list"
          class="mt-2 flex flex-wrap gap-1.5"
        >
          <li
            v-for="phase in phases"
            :key="phase.name"
            class="inline-flex items-center gap-1.5 rounded-md bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
          >
            {{ phase.phase_name }}
            <span class="font-mono tabular-nums text-ink-gray-5">
              {{ phase.completed_count }}/{{ phase.total_count }}
            </span>
          </li>
        </ul>
      </div>
    </div>

    <!-- Actions: navigation on the left, changes on the right -->
    <footer
      class="flex items-center gap-1 border-t border-outline-gray-2 px-2 py-1.5"
    >
      <Button
        variant="ghost"
        :label="__('Open')"
        @click="
          router.push({
            name: 'TaskyProject',
            params: { projectId: project.name },
          })
        "
      >
        <template #prefix>
          <LucideLayoutDashboard class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <Button
        variant="ghost"
        :label="__('Board')"
        @click="
          router.push({
            name: 'TaskyKanban',
            params: { projectId: project.name },
          })
        "
      >
        <template #prefix>
          <LucideKanban class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <Button
        v-if="project.file_count"
        variant="ghost"
        :aria-label="__('{0} files', String(project.file_count))"
        @click="
          router.push({
            name: 'TaskyFiles',
            params: { projectId: project.name },
          })
        "
      >
        <template #prefix>
          <LucidePaperclip class="size-4" aria-hidden="true" />
        </template>
        <span class="font-mono tabular-nums">{{ project.file_count }}</span>
      </Button>
      <div class="ml-auto flex items-center gap-1">
        <Button
          v-if="project.can_add_tasks"
          :label="__('New task')"
          @click="emit('new-task')"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Dropdown v-if="moreActions.length" :options="moreActions" align="end">
          <Button
            variant="ghost"
            :aria-label="
              __('More actions for {0}', project.project_name || project.name)
            "
          >
            <template #icon>
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { FILL, TRACK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { Button, Dropdown, dayjs } from "frappe-ui";
import { computed, ref, useId } from "vue";
import { RouterLink, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideKanban from "~icons/lucide/square-kanban";
import { projectEndNote } from "../taskMeta";
import TaskStatusBadge from "./TaskStatusBadge.vue";

export interface ProjectSummary {
  name: string;
  project_name?: string;
  status?: string;
  expected_start_date?: string;
  expected_end_date?: string;
  customer?: string;
  project_lead?: string;
  project_lead_name?: string;
  department?: string;
  can_manage?: boolean;
  can_edit?: boolean;
  can_add_tasks?: boolean;
  file_count?: number;
}

export interface ProjectStats {
  total: number;
  completed: number;
  in_progress: number;
  reviewing: number;
  on_hold: number;
  overdue: number;
  completion_pct: number;
}

export interface ProjectPhase {
  name: string;
  phase_name: string;
  completed_count: number;
  total_count: number;
}

const props = defineProps<{
  project: ProjectSummary;
  stats?: ProjectStats | null;
  phases: ProjectPhase[];
  loading?: boolean;
  failed?: boolean;
}>();

const emit = defineEmits<{
  (e: "new-task"): void;
  (e: "edit"): void;
  (e: "checklist"): void;
}>();

const router = useRouter();
const headingId = `project-card-${useId()}`;
const phasesId = `project-phases-${useId()}`;
const showPhases = ref(false);

const dateRange = computed(() => {
  const p = props.project;
  const fmt = (d: string) => dayjs(d).format("D MMM YYYY");
  if (p.expected_start_date && p.expected_end_date)
    return `${fmt(p.expected_start_date)} – ${fmt(p.expected_end_date)}`;
  if (p.expected_start_date) return __("From {0}", fmt(p.expected_start_date));
  if (p.expected_end_date) return __("Due {0}", fmt(p.expected_end_date));
  return __("No dates set");
});

const endNote = computed(() => projectEndNote(props.project));

const barTone = computed<Tone>(() =>
  props.project.status === "Completed" ? "success" : "neutral"
);

const moreActions = computed(() => {
  const actions: { label: string; icon: unknown; onClick: () => void }[] = [];
  if (props.project.can_edit)
    actions.push({
      label: __("Edit project"),
      icon: LucidePencil,
      onClick: () => emit("edit"),
    });
  if (props.project.can_manage)
    actions.push({
      label: __("Generate checklist"),
      icon: LucideClipboardList,
      onClick: () => emit("checklist"),
    });
  return actions;
});
</script>
