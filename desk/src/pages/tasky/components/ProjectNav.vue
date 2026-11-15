<template>
  <LayoutHeader>
    <template #left-header>
      <!-- back to the previous page (a parent folder, the last tab, the list you came
           from); the project list when the page was opened directly (owner's request,
           2026-10-14) -->
      <Button
        size="md"
        class="me-1 shrink-0"
        :label="__('Back')"
        :tooltip="__('Back')"
        @click="goBack"
      >
        <template #icon>
          <LucideArrowLeft class="size-[18px]" aria-hidden="true" />
        </template>
      </Button>
      <nav
        class="flex min-w-0 items-center gap-1.5 text-lg md:text-[22px] md:leading-[1.2] md:tracking-[-0.01em]"
        :aria-label="__('Breadcrumb')"
      >
        <!-- below md the Back button stands in for this link, so the project name fits -->
        <router-link
          :to="{ name: 'TaskyProjects' }"
          class="hidden shrink-0 rounded font-medium text-ink-gray-6 transition-colors hover:text-ink-gray-9 md:inline"
        >
          {{ __("Projects") }}
        </router-link>
        <LucideChevronRight
          class="hidden size-4 shrink-0 text-ink-gray-4 md:block"
          aria-hidden="true"
        />
        <span
          v-if="detail.loading && !detail.data"
          class="inline-block h-5 w-40 animate-pulse rounded bg-surface-gray-3"
        />
        <span
          v-else
          class="truncate font-bold text-ink-gray-9"
          aria-current="page"
        >
          {{ detail.data?.project_name || projectId }}
        </span>
      </nav>
    </template>
    <template #right-header>
      <slot name="actions" />
      <!-- below lg the secondary actions show only their icons in a 44px target
           (the label stays as the accessible name), so they fit beside the breadcrumb -->
      <Button
        v-if="detail.data?.can_change_lead"
        size="md"
        :label="__('Edit project')"
        @click="showEdit = true"
      >
        <template #prefix
          ><LucidePencil class="size-[18px]" aria-hidden="true"
        /></template>
        <span class="hidden lg:inline">{{ __("Edit project") }}</span>
      </Button>
      <Dropdown v-if="detail.data?.can_change_lead" :options="leadOptions">
        <Button size="md" :loading="changingLead" :label="leadLabel">
          <template #prefix
            ><LucideUserStar class="size-[18px]" aria-hidden="true"
          /></template>
          <span class="hidden max-w-48 truncate lg:inline">{{
            leadLabel
          }}</span>
          <template #suffix
            ><LucideChevronDown
              class="hidden size-4 sm:block"
              aria-hidden="true"
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
        size="md"
        :label="__('New task')"
        @click="showNewTask = true"
      >
        <template #prefix
          ><LucidePlus class="size-[18px]" aria-hidden="true"
        /></template>
        <span class="hidden sm:inline">{{ __("New task") }}</span>
      </Button>
    </template>
  </LayoutHeader>

  <!-- the project's sections as pills on the canvas, the current one filled dark -->
  <div class="shrink-0 px-4 pt-5 md:px-8">
    <nav
      class="inline-flex max-w-full gap-1 overflow-x-auto rounded-full border border-outline-gray-2 bg-surface-base p-1"
      :aria-label="__('Project sections')"
    >
      <router-link
        v-for="tab in visibleTabs"
        :key="tab.to"
        :to="{ name: tab.to, params: { projectId } }"
        class="inline-flex h-10 shrink-0 items-center gap-2 rounded-full px-3.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
        :class="
          isCurrent(tab)
            ? 'bg-surface-gray-10 text-ink-base'
            : 'text-ink-gray-7 hover:bg-surface-gray-3'
        "
        :aria-current="isCurrent(tab) ? 'page' : undefined"
      >
        <component :is="tab.icon" class="size-4" aria-hidden="true" />
        {{ __(tab.label) }}
        <span
          v-if="tab.to === 'TaskyFiles' && detail.data?.file_count"
          class="min-w-[22px] rounded-full px-[7px] py-px text-center text-xs font-semibold tabular-nums"
          :class="
            isCurrent(tab)
              ? 'bg-white/20 text-ink-base'
              : 'bg-surface-gray-4 text-ink-gray-7'
          "
          :aria-label="__('{0} files', String(detail.data.file_count))"
        >
          {{ detail.data.file_count }}
        </span>
      </router-link>
    </nav>
  </div>

  <p
    v-if="showsOwnTasksOnly"
    class="mx-4 mt-4 flex shrink-0 items-start gap-2 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3 text-p-sm text-ink-gray-6 md:mx-8"
  >
    <LucideEyeOff
      class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
      aria-hidden="true"
    />
    {{
      __(
        "You see your own tasks in this project: the ones assigned to you and the ones you gave out. The project's manager, lead and coordinators see every task."
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
    v-if="detail.data?.can_add_tasks"
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
import { useGoBack } from "@/composables/goBack";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, call, createResource, Dropdown, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideCoins from "~icons/lucide/coins";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideRepeat from "~icons/lucide/repeat";
import LucideMegaphone from "~icons/lucide/megaphone";
import LucideShare2 from "~icons/lucide/share-2";
import LucideUserStar from "~icons/lucide/user-star";
import LucideUserX from "~icons/lucide/user-x";
import LucideKanban from "~icons/lucide/square-kanban";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideKeyRound from "~icons/lucide/key-round";
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

const { goBack } = useGoBack({ name: "TaskyProjects" });
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
    label: "Credentials",
    to: "TaskyCredentials",
    icon: LucideKeyRound,
    // only the project's managers, lead and department head; the server decides
    needs: "can_handle_credentials",
  },
  {
    label: "Meta",
    to: "TaskyMeta",
    icon: LucideShare2,
    // the same people as Credentials: whoever handles the client's accounts
    needs: "can_handle_credentials",
  },
  {
    label: "Ads",
    to: "TaskyAds",
    icon: LucideMegaphone,
    // boosts and their spend, for whoever handles the client's accounts
    needs: "can_handle_credentials",
  },
  {
    label: "Commission",
    to: "TaskyCommission",
    icon: LucideCoins,
    // managers only; the ERP site decides who may read or change a project's commission
    needs: "@manager",
  },
  {
    label: "Sign-off",
    to: "TaskySignoffs",
    icon: LucideClipboardCheck,
    // a single sign-off stays under this tab
    also: ["TaskySignoff"],
  },
];

const auth = useAuthStore();
const visibleTabs = computed(() =>
  tabs.filter(
    (tab) =>
      !tab.needs ||
      (tab.needs === "@manager"
        ? auth.isAdmin || auth.isManager
        : detail.data?.[tab.needs])
  )
);

function isCurrent(tab: { to: string; also?: string[] }) {
  const name = String(route.name);
  return name === tab.to || !!tab.also?.includes(name);
}

// the tabs that list the project's tasks (Files, Credentials, Meta and Sign-off don't)
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
  // runs the tasks (edit, plan, review): managers, the lead and coordinators
  canCoordinate: computed(() => !!detail.data?.can_coordinate),
  openNewTask: () => (showNewTask.value = true),
  reload: () => detail.reload(),
});
</script>
