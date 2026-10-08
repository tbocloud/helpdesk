<template>
  <div>
    <div class="flex items-center justify-between gap-3 pb-4">
      <h2 class="text-lg-semibold text-ink-gray-9">{{ __("Projects") }}</h2>
      <RouterLink
        :to="{ name: 'TaskyProjects', query: { q: customerName } }"
        class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      >
        {{ __("Open in Projects") }}
      </RouterLink>
    </div>

    <div
      v-if="projects.loading && !projects.data"
      class="overflow-hidden rounded-lg border border-outline-gray-2"
      :aria-label="__('Loading')"
    >
      <div
        v-for="i in 3"
        :key="i"
        class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
      >
        <span class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2" />
        <span class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2" />
      </div>
    </div>

    <TaskyState
      v-else-if="projects.error && !projects.data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the projects')"
      :message="errorText(projects.error, __('Try again.'))"
      error
    >
      <Button :label="__('Retry')" @click="projects.reload()" />
    </TaskyState>

    <TaskyState
      v-else-if="!sorted.length"
      :icon="LucideFolderKanban"
      :title="__('No projects for this customer')"
      :message="
        __(
          'Projects show up here once this customer is set on them. You only see projects you are on, lead or manage.'
        )
      "
    />

    <p
      v-if="moreNote && sorted.length"
      class="mb-3 text-p-sm tabular-nums text-ink-gray-6"
      role="status"
    >
      {{ moreNote }}
    </p>
    <ul
      v-if="sorted.length"
      role="list"
      class="overflow-hidden rounded-lg border border-outline-gray-2"
    >
      <li
        v-for="project in sorted"
        :key="project.name"
        class="border-b border-outline-gray-1 last:border-b-0"
      >
        <RouterLink
          :to="{ name: 'TaskyProject', params: { projectId: project.name } }"
          class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
        >
          <span class="min-w-0">
            <span class="block truncate text-sm text-ink-gray-9">
              {{ project.project_name || project.name }}
            </span>
            <span
              class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
            >
              <span class="font-mono">{{ project.name }}</span>
              <template v-if="project.project_lead">
                <span aria-hidden="true">·</span>
                <span class="truncate">
                  {{ __("Lead: {0}", leadName(project.project_lead)) }}
                </span>
              </template>
            </span>
          </span>
          <span class="flex flex-wrap items-center justify-end gap-2">
            <span
              v-if="project.note"
              class="flex items-center gap-1 text-xs tabular-nums"
              :class="project.note.late ? 'text-danger' : 'text-ink-gray-6'"
            >
              <LucideCalendarX2
                v-if="project.note.late"
                class="size-3.5"
                aria-hidden="true"
              />
              {{ project.note.text }}
            </span>
            <TaskyBadge
              v-if="project.status !== 'Open'"
              :label="__(project.status)"
              :tone="project.status === 'Completed' ? 'success' : 'neutral'"
            />
          </span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { projectEndNote } from "@/pages/tasky/taskMeta";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { CustomerResourceSymbol } from "@/types";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import { computed, inject } from "vue";
import { RouterLink } from "vue-router";
import LucideCalendarX2 from "~icons/lucide/calendar-x-2";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFolderKanban from "~icons/lucide/folder-kanban";

interface ProjectRow {
  name: string;
  project_name: string;
  status: "Open" | "On hold" | "Completed" | "Cancelled";
  expected_end_date: string | null;
  project_lead: string | null;
}

const props = defineProps<{
  projects: {
    data?: ProjectRow[] | null;
    loading: boolean;
    error?: unknown;
    hasNextPage?: boolean;
    reload: () => void;
  };
  /** every project the viewer may see, when known; the list holds only the latest */
  total?: number;
}>();

const moreNote = computed(() => {
  const shown = props.projects.data?.length ?? 0;
  if (props.total !== undefined && props.total > shown)
    return __(
      "Showing the {0} most recently updated of {1}. Open in Projects to see them all.",
      String(shown),
      String(props.total)
    );
  if (props.total === undefined && props.projects.hasNextPage && shown)
    return __(
      "Showing the {0} most recently updated; there are more. Open in Projects to see them all.",
      String(shown)
    );
  return "";
});

const customer = inject(CustomerResourceSymbol)!;
const { getUser } = useUserStore();

// open work first, then on hold, then the finished ones; soonest end date first
const STATUS_ORDER = ["Open", "On hold", "Completed", "Cancelled"];

const customerName = computed(
  () => customer.doc?.customer_name || customer.doc?.name || ""
);

const sorted = computed(() =>
  [...(props.projects.data ?? [])]
    .sort(
      (a, b) =>
        STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
        (a.expected_end_date || "9999").localeCompare(
          b.expected_end_date || "9999"
        )
    )
    .map((project) => ({ ...project, note: projectEndNote(project) }))
);

function leadName(email: string) {
  return getUser(email)?.full_name || email;
}
</script>
