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
      <!-- below md the secondary actions show only their icons in a 44px target
           (the label stays as the accessible name), so they fit beside the breadcrumb -->
      <Button
        v-if="detail.data?.can_change_lead"
        variant="ghost"
        :label="__('Edit project')"
        @click="showEdit = true"
      >
        <template #prefix
          ><LucidePencil class="size-4" aria-hidden="true"
        /></template>
        <span class="hidden md:inline">{{ __("Edit project") }}</span>
      </Button>
      <Dropdown v-if="detail.data?.can_change_lead" :options="leadOptions">
        <Button :loading="changingLead" :label="leadLabel">
          <template #prefix
            ><LucideUserStar class="size-4" aria-hidden="true"
          /></template>
          <span class="hidden max-w-48 truncate md:inline">{{
            leadLabel
          }}</span>
          <template #suffix
            ><LucideChevronDown class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </Dropdown>
      <span
        v-else-if="detail.data"
        class="hidden items-center gap-1.5 text-sm text-ink-gray-6 sm:flex"
      >
        <LucideUserStar class="size-4" aria-hidden="true" />
        {{ leadLabel }}
      </span>
      <Button
        v-if="detail.data?.can_add_tasks"
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
        isCurrent(tab)
          ? 'border-brand text-ink-gray-9'
          : 'border-transparent text-ink-gray-5 hover:text-ink-gray-8'
      "
      :aria-current="isCurrent(tab) ? 'page' : undefined"
    >
      <component :is="tab.icon" class="size-4" aria-hidden="true" />
      {{ __(tab.label) }}
      <span
        v-if="tab.to === 'TaskyFiles' && detail.data?.file_count"
        class="rounded bg-surface-gray-2 px-1.5 font-mono text-xs tabular-nums text-ink-gray-6"
        :aria-label="__('{0} files', String(detail.data.file_count))"
      >
        {{ detail.data.file_count }}
      </span>
    </router-link>
  </nav>

  <p
    v-if="showsOwnTasksOnly"
    class="flex shrink-0 items-start gap-2 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-p-sm text-ink-gray-6 md:px-5"
  >
    <LucideEyeOff
      class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
      aria-hidden="true"
    />
    {{
      __(
        "You see your own tasks in this project: the ones assigned to you and the ones you gave out. The project's manager and lead see every task."
      )
    }}
  </p>

  <ProjectFormDialog
    v-if="detail.data?.can_change_lead"
    v-model:open="showEdit"
    :project-id="projectId"
    @saved="detail.reload()"
  />

  <NewTaskDialog
    v-if="detail.data?.can_manage"
    v-model:open="showNewTask"
    :project-id="projectId"
    :phases="phases"
    @created="emit('taskCreated')"
  />
</template>

<script lang="ts">
// the project last recorded as opened, so moving between its tabs doesn't record it again
let lastRecorded = "";
</script>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, call, createResource, Dropdown, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideRepeat from "~icons/lucide/repeat";
import LucideUserStar from "~icons/lucide/user-star";
import LucideUserX from "~icons/lucide/user-x";
import LucideKanban from "~icons/lucide/square-kanban";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import NewTaskDialog from "./NewTaskDialog.vue";
import ProjectFormDialog from "./ProjectFormDialog.vue";

const props = defineProps<{
  projectId: string;
  /** Existing phase names, offered as suggestions in the new-task dialog. */
  phases?: string[];
}>();

const emit = defineEmits<{ taskCreated: [] }>();

const route = useRoute();
const showNewTask = ref(false);
const showEdit = ref(false);

const tabs = [
  { label: "Dashboard", to: "TaskyProject", icon: LucideLayoutDashboard },
  { label: "Checklist", to: "TaskyChecklist", icon: LucideListChecks },
  { label: "Board", to: "TaskyKanban", icon: LucideKanban },
  { label: "Timeline", to: "TaskyTimeline", icon: LucideCalendarRange },
  { label: "Overdue", to: "TaskyOverdue", icon: LucideAlarmClock },
  { label: "Recurring", to: "TaskyRecurring", icon: LucideRepeat },
  { label: "Files", to: "TaskyFiles", icon: LucidePaperclip },
  {
    label: "Sign-off",
    to: "TaskySignoffs",
    icon: LucideClipboardCheck,
    // a single sign-off stays under this tab
    also: ["TaskySignoff"],
  },
];

function isCurrent(tab: { to: string; also?: string[] }) {
  const name = String(route.name);
  return name === tab.to || !!tab.also?.includes(name);
}

// the tabs that list the project's tasks (Files and Sign-off don't)
const TASK_TABS = [
  "TaskyProject",
  "TaskyChecklist",
  "TaskyKanban",
  "TaskyTimeline",
  "TaskyOverdue",
  "TaskyRecurring",
];

const showsOwnTasksOnly = computed(
  () =>
    !!detail.data &&
    !detail.data.sees_all_tasks &&
    TASK_TABS.includes(String(route.name))
);

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

// once the project has loaded (so it can be read), it goes to the top of Recent
// projects; Recent is a convenience, so a failure stays silent
watch(
  () => detail.data?.name as string | undefined,
  (name) => {
    if (!name || name === lastRecorded) return;
    lastRecorded = name;
    call("helpdesk.tasky.api.record_project_view", { project: name }).catch(
      () => (lastRecorded = "")
    );
  }
);

// --- project lead: one developer per project, rotated by the project's manager ---

const changingLead = ref(false);

const leadLabel = computed(() =>
  detail.data?.project_lead_name || detail.data?.project_lead
    ? __("Lead: {0}", detail.data.project_lead_name || detail.data.project_lead)
    : __("No lead")
);

async function changeLead(method: string, args: Record<string, unknown>) {
  changingLead.value = true;
  try {
    const res = await call(`helpdesk.tasky.api.${method}`, {
      project: props.projectId,
      ...args,
    });
    await detail.reload();
    toast.success(
      res?.project_lead
        ? __(
            "{0} is now the project lead",
            detail.data?.project_lead_name || res.project_lead
          )
        : __("Project lead removed")
    );
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't change the project lead"));
  } finally {
    changingLead.value = false;
  }
}

const leadOptions = computed(() => {
  const members = (detail.data?.users ?? []) as {
    user: string;
    full_name?: string;
    role?: string;
  }[];
  // developers first: the lead normally rotates among them
  const sorted = [...members].sort(
    (a, b) => Number(b.role === "Developer") - Number(a.role === "Developer")
  );
  return [
    {
      group: __("Make lead"),
      items: sorted.map((m) => ({
        label: `${m.full_name || m.user}${
          m.user === detail.data?.project_lead ? " \u2713" : ""
        }`,
        onClick: () => changeLead("set_project_lead", { user: m.user }),
      })),
    },
    {
      group: __("Actions"),
      items: [
        {
          label: __("Rotate to next developer"),
          icon: LucideRefreshCw,
          onClick: () => changeLead("rotate_project_lead", {}),
        },
        ...(detail.data?.project_lead
          ? [
              {
                label: __("Remove lead"),
                icon: LucideUserX,
                onClick: () => changeLead("set_project_lead", { user: "" }),
              },
            ]
          : []),
      ],
    },
  ];
});

defineExpose({
  canManage: computed(() => !!detail.data?.can_manage),
  openNewTask: () => (showNewTask.value = true),
  reload: () => detail.reload(),
});
</script>
