<template>
  <LayoutHeader>
    <template #left-header>
      <nav
        class="flex min-w-0 items-center gap-1.5 text-lg-medium"
        :aria-label="__('Breadcrumb')"
      >
        <router-link
          :to="{ name: 'TaskyProjects' }"
          class="shrink-0 rounded text-ink-gray-5 transition-colors hover:text-ink-gray-8"
        >
          {{ __("Projects") }}
        </router-link>
        <LucideChevronRight
          class="size-4 shrink-0 text-ink-gray-4"
          aria-hidden="true"
        />
        <span
          v-if="detail.loading && !detail.data"
          class="inline-block h-4 w-32 animate-pulse rounded bg-surface-gray-2"
        />
        <span v-else class="truncate text-ink-gray-9" aria-current="page">
          {{ detail.data?.project_name || projectId }}
        </span>
      </nav>
    </template>
    <template #right-header>
      <slot name="actions" />
      <Button
        v-if="detail.data?.can_manage"
        variant="solid"
        :label="__('New task')"
        @click="showNewTask = true"
      >
        <template #prefix
          ><LucidePlus class="size-4" aria-hidden="true"
        /></template>
      </Button>
    </template>
  </LayoutHeader>

  <nav
    class="flex shrink-0 gap-1 overflow-x-auto border-b border-outline-gray-2 bg-surface-base px-3 md:px-4"
    :aria-label="__('Project sections')"
  >
    <router-link
      v-for="tab in tabs"
      :key="tab.to"
      :to="{ name: tab.to, params: { projectId } }"
      class="-mb-px flex h-10 shrink-0 items-center gap-1.5 border-b-2 px-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
      :class="
        route.name === tab.to
          ? 'border-brand text-ink-gray-9'
          : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'
      "
      :aria-current="route.name === tab.to ? 'page' : undefined"
    >
      <component :is="tab.icon" class="size-4" aria-hidden="true" />
      {{ __(tab.label) }}
    </router-link>
  </nav>

  <NewTaskDialog
    v-if="detail.data?.can_manage"
    v-model:open="showNewTask"
    :project-id="projectId"
    :phases="phases"
    @created="emit('taskCreated')"
  />
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideKanban from "~icons/lucide/square-kanban";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePlus from "~icons/lucide/plus";
import NewTaskDialog from "./NewTaskDialog.vue";

const props = defineProps<{
  projectId: string;
  /** Existing phase names, offered as suggestions in the new-task dialog. */
  phases?: string[];
}>();

const emit = defineEmits<{ taskCreated: [] }>();

const route = useRoute();
const showNewTask = ref(false);

const tabs = [
  { label: "Dashboard", to: "TaskyProject", icon: LucideLayoutDashboard },
  { label: "Checklist", to: "TaskyChecklist", icon: LucideListChecks },
  { label: "Board", to: "TaskyKanban", icon: LucideKanban },
  { label: "Timeline", to: "TaskyTimeline", icon: LucideCalendarRange },
  { label: "Overdue", to: "TaskyOverdue", icon: LucideAlarmClock },
];

const detail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: props.projectId }),
  // the page body reports load failures; the breadcrumb falls back to the ID
  onError() {},
});

watch(
  () => props.projectId,
  (id) => {
    if (id) detail.reload();
  },
  { immediate: true }
);

defineExpose({
  canManage: computed(() => !!detail.data?.can_manage),
  openNewTask: () => (showNewTask.value = true),
});
</script>
