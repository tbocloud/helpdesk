<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="truncate text-lg-medium text-ink-gray-9">
          {{ pageTitle }}
        </div>
      </template>
      <template #right-header>
        <!-- leads and managers can open a team member's list -->
        <div v-if="authStore.canSeeOverview" class="w-44 sm:w-56">
          <Autocomplete
            :options="personOptions"
            :placeholder="__('Show work for…')"
            :model-value="viewUser || null"
            @update:model-value="
              (v: { value: string } | string | null) =>
                (viewUser = (typeof v === 'string' ? v : v?.value) || '')
            "
          />
        </div>
        <Button
          variant="ghost"
          :loading="work.loading"
          :aria-label="__('Refresh')"
          @click="work.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <!-- whose work this is, when it isn't yours -->
        <div
          v-if="viewUser"
          class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          role="status"
        >
          <div class="flex min-w-0 items-center gap-3">
            <Avatar
              shape="circle"
              size="md"
              :image="userStore.getUser(viewUser)?.user_image"
              :label="viewName"
              aria-hidden="true"
            />
            <p class="min-w-0 text-p-sm text-ink-gray-7">
              <span class="text-ink-gray-9">{{
                __("You're looking at {0}'s work.", viewName)
              }}</span>
              {{
                __(
                  "Only they can start, complete or pause it; you can plan and review tasks on projects you lead."
                )
              }}
            </p>
          </div>
          <Button
            class="shrink-0 self-start sm:self-auto"
            :label="__('Back to my work')"
            @click="viewUser = ''"
          >
            <template #prefix>
              <LucideArrowLeft class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <p v-else class="text-p-sm text-ink-gray-6">
          {{
            __(
              "What's on your plate, most urgent first. Start, finish or pause work right from the list."
            )
          }}
        </p>

        <TaskyState
          v-if="work.error && !work.data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="
            viewUser
              ? __('Couldn\'t load {0}\'s work', viewName)
              : __('Couldn\'t load your work')
          "
          :message="
            errorText(work.error, __('Check your connection and try again.'))
          "
          error
        >
          <Button :label="__('Retry')" @click="work.reload()" />
        </TaskyState>

        <template v-else>
          <div
            class="-mx-1 mt-4 flex gap-1 overflow-x-auto px-1"
            role="tablist"
            :aria-label="__('Filter work')"
          >
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              role="tab"
              :aria-selected="activeTab === tab.key"
              :aria-controls="listId"
              class="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :class="
                activeTab === tab.key
                  ? 'bg-surface-gray-3 text-ink-gray-9'
                  : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
              "
              @click="activeTab = tab.key"
            >
              <component
                :is="tab.icon"
                v-if="tab.icon"
                class="size-3.5"
                aria-hidden="true"
              />
              {{ tab.label }}
              <span
                class="rounded px-1 font-mono text-xs tabular-nums"
                :class="
                  activeTab === tab.key
                    ? 'bg-surface-base text-ink-gray-8'
                    : 'text-ink-gray-5'
                "
              >
                <span
                  v-if="isLoading"
                  class="inline-block h-3 w-3 animate-pulse rounded bg-surface-gray-2 align-middle"
                />
                <template v-else>{{ countFor(tab.key) }}</template>
              </span>
            </button>
          </div>

          <div :id="listId" class="mt-4" :aria-busy="work.loading">
            <!-- Loading -->
            <div
              v-if="isLoading"
              class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
              :aria-label="__('Loading')"
            >
              <div
                v-for="i in 6"
                :key="i"
                class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
              >
                <div class="size-4 animate-pulse rounded bg-surface-gray-2" />
                <div class="flex flex-1 flex-col gap-2">
                  <div
                    class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                  />
                </div>
                <div
                  class="hidden h-3 w-20 animate-pulse rounded bg-surface-gray-2 md:block"
                />
              </div>
            </div>

            <!-- Completed work -->
            <SectionCard
              v-else-if="activeTab === 'done'"
              :title="__('Completed in the last 30 days')"
              :count="doneItems.length"
              class="overflow-hidden"
            >
              <div
                v-if="doneItems.length"
                class="hidden grid-cols-[1fr_8rem_5rem] gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
                aria-hidden="true"
              >
                <span>{{ __("Work") }}</span>
                <span>{{ __("Completed") }}</span>
                <span class="text-right">{{ __("Hours") }}</span>
              </div>
              <ul v-if="doneItems.length" role="list">
                <li
                  v-for="item in doneItems"
                  :key="`${item.kind}:${item.name}`"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <component
                    :is="doneRoute(item) ? 'router-link' : 'div'"
                    :to="doneRoute(item) || undefined"
                    class="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 md:grid-cols-[1fr_8rem_5rem]"
                  >
                    <div class="flex min-w-0 items-start gap-2.5">
                      <LucideCircleCheck
                        class="mt-0.5 size-4 shrink-0 text-success"
                        aria-hidden="true"
                      />
                      <div class="min-w-0">
                        <div class="truncate text-sm text-ink-gray-9">
                          {{ item.title }}
                        </div>
                        <div
                          class="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-ink-gray-5"
                        >
                          <span>{{
                            item.kind === "task" ? __("Task") : __("Ticket")
                          }}</span>
                          <span class="font-mono">{{ item.name }}</span>
                          <template v-if="item.project_name || item.customer">
                            <span aria-hidden="true">·</span>
                            <span class="truncate">{{
                              item.project_name || item.customer
                            }}</span>
                          </template>
                        </div>
                      </div>
                    </div>
                    <span
                      class="font-mono text-xs tabular-nums text-ink-gray-7"
                    >
                      {{
                        item.done_on
                          ? dayjs(item.done_on).format("D MMM YYYY")
                          : "—"
                      }}
                    </span>
                    <span
                      class="hidden text-right font-mono text-xs tabular-nums text-ink-gray-7 md:block"
                    >
                      {{
                        item.hours != null
                          ? `${Math.round(item.hours * 100) / 100}h`
                          : "—"
                      }}
                    </span>
                  </component>
                </li>
              </ul>
              <TaskyState
                v-else
                :icon="LucideCircleCheck"
                :title="__('Nothing completed lately')"
                :message="
                  __(
                    'Tasks completed and tickets resolved in the last 30 days show up here.'
                  )
                "
              />
            </SectionCard>

            <!-- Empty: nothing open, or the filter matches nothing -->
            <div
              v-else-if="!visibleItems.length"
              class="rounded-lg border border-outline-gray-2 bg-surface-base"
            >
              <TaskyState
                :icon="emptyState.icon"
                :title="emptyState.title"
                :message="emptyState.message"
              >
                <Button
                  v-if="activeTab !== 'all'"
                  :label="__('Show all')"
                  @click="activeTab = 'all'"
                />
              </TaskyState>
            </div>

            <!-- Open work, by when it's due -->
            <div v-else class="flex flex-col gap-4">
              <SectionCard
                v-for="group in groups"
                :key="group.key"
                :title="group.label"
                :count="group.items.length"
                :description="group.description"
                :icon="group.icon"
                :icon-class="group.iconClass"
                class="overflow-hidden"
              >
                <ul role="list">
                  <li
                    v-for="item in group.items"
                    :key="itemKey(item)"
                    class="border-b border-outline-gray-1 last:border-b-0"
                  >
                    <WorkItemRow :item="item">
                      <template v-if="item.kind === 'task'" #actions>
                        <WorkItemActions
                          :item="item"
                          :mine="!viewUser"
                          :busy="busy === item.name"
                          @step="onStep"
                        />
                      </template>
                    </WorkItemRow>
                  </li>
                </ul>
              </SectionCard>
            </div>
          </div>
        </template>
      </div>
    </div>

    <TaskDetailDialog
      v-model:task="detailTask"
      :action="detailAction"
      :mine="!viewUser"
      @changed="work.reload()"
    />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import TaskyState from "@/components/TaskyState.vue";
import TaskDetailDialog, {
  type TaskAction,
  type TaskRef,
} from "@/pages/tasky/components/TaskDetailDialog.vue";
import { useApproveTask } from "@/pages/tasky/useApproveTask";
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Autocomplete,
  Avatar,
  Button,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideEye from "~icons/lucide/eye";
import LucideInbox from "~icons/lucide/inbox";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideStar from "~icons/lucide/star";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import WorkItemActions, {
  type WorkStep,
} from "./components/WorkItemActions.vue";
import WorkItemRow from "./components/WorkItemRow.vue";
import {
  DUE_GROUPS,
  dueGroup,
  isAtRisk,
  itemKey,
  type DueGroup,
  type WorkItem,
} from "./workMeta";

type Tab = "all" | "overdue" | "at_risk" | "key" | "task" | "ticket" | "done";

interface DoneItem {
  kind: "task" | "ticket";
  name: string;
  title: string;
  project?: string | null;
  project_name?: string | null;
  customer?: string | null;
  status: string;
  done_on: string | null;
  hours: number | null;
}

interface MyWork {
  items: WorkItem[];
  done?: DoneItem[];
  counts: { total: number; overdue: number; key: number; at_risk?: number };
}

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const userStore = useUserStore();
const listId = `my-work-list-${useId()}`;

const viewUser = ref((route.query.user as string) || "");

const work = createResource({
  url: "helpdesk.api.work.get_my_work",
  makeParams: () => ({ user: viewUser.value || undefined }),
  auto: true,
});

const isLoading = computed(() => work.loading && !work.data);

const people = createResource({
  url: "helpdesk.tasky.api.get_users",
  auto: authStore.canSeeOverview,
});

const personOptions = computed(() => [
  { label: __("Me"), value: "" },
  ...((people.data ?? []) as { name: string; full_name?: string }[])
    .filter((p) => p.name !== authStore.userId)
    .map((p) => ({
      label: p.full_name || p.name,
      value: p.name,
      description: p.name,
    })),
]);

const viewName = computed(() => {
  const person = (
    (people.data ?? []) as { name: string; full_name?: string }[]
  ).find((p) => p.name === viewUser.value);
  return (
    person?.full_name ||
    userStore.getUser(viewUser.value)?.full_name ||
    viewUser.value
  );
});

const pageTitle = computed(() =>
  viewUser.value ? __("Work of {0}", viewName.value) : __("My Work")
);

watch(viewUser, (user) => {
  router.replace({ query: { ...route.query, user: user || undefined } });
  work.reload();
});

const tabs = computed<{ key: Tab; label: string; icon?: Component }[]>(() => [
  { key: "all", label: __("All") },
  { key: "overdue", label: __("Overdue"), icon: LucideAlarmClock },
  { key: "at_risk", label: __("At risk"), icon: LucideTriangleAlert },
  { key: "key", label: __("Key"), icon: LucideStar },
  { key: "task", label: __("Tasks") },
  { key: "ticket", label: __("Tickets") },
  { key: "done", label: __("Completed"), icon: LucideCircleCheck },
]);

const TAB_KEYS: Tab[] = [
  "all",
  "overdue",
  "at_risk",
  "key",
  "task",
  "ticket",
  "done",
];

const activeTab = ref<Tab>(
  TAB_KEYS.includes(route.query.tab as Tab) ? (route.query.tab as Tab) : "all"
);

// keep the tab in the URL so it survives reloads and can be shared
watch(activeTab, (tab) => {
  router.replace({
    query: { ...route.query, tab: tab === "all" ? undefined : tab },
  });
});

const items = computed<WorkItem[]>(
  () => (work.data as MyWork | undefined)?.items ?? []
);

function matches(item: WorkItem, tab: Tab) {
  if (tab === "all") return true;
  if (tab === "overdue") return item.is_overdue;
  if (tab === "at_risk") return isAtRisk(item);
  if (tab === "key") return item.is_key;
  return item.kind === tab;
}

const doneItems = computed<DoneItem[]>(
  () => (work.data as MyWork | undefined)?.done ?? []
);

function countFor(tab: Tab) {
  if (tab === "done") return doneItems.value.length;
  return items.value.filter((i) => matches(i, tab)).length;
}

function doneRoute(item: DoneItem) {
  if (item.kind === "ticket")
    return { name: "TicketAgent", params: { ticketId: item.name } };
  if (item.project)
    return { name: "TaskyProject", params: { projectId: item.project } };
  return null;
}

// the server already orders overdue → key → deadline
const visibleItems = computed(() =>
  items.value.filter((i) => matches(i, activeTab.value))
);

interface GroupMeta {
  label: string;
  description: string;
  icon?: Component;
  iconClass?: string;
}

const GROUP_META = computed<Record<DueGroup, GroupMeta>>(() => ({
  overdue: {
    label: __("Overdue"),
    description: __("Past the due date or the SLA. Start here."),
    icon: LucideAlarmClock,
    iconClass: "text-danger",
  },
  today: { label: __("Today"), description: __("Due by the end of today.") },
  week: { label: __("This week"), description: __("Due in the next 7 days.") },
  later: {
    label: __("Later"),
    description: __("Due after next week, or no date set yet."),
  },
  on_hold: {
    label: __("On hold"),
    description: __("Paused. Resume when what's blocking it clears."),
    icon: LucidePause,
  },
  review: {
    label: __("In review"),
    description: __("Finished and waiting for a lead or manager to sign off."),
    icon: LucideEye,
  },
}));

const groups = computed(() => {
  const byGroup = new Map<DueGroup, WorkItem[]>();
  for (const item of visibleItems.value) {
    const key = dueGroup(item);
    if (!byGroup.has(key)) byGroup.set(key, []);
    byGroup.get(key)!.push(item);
  }
  return DUE_GROUPS.filter((key) => byGroup.has(key)).map((key) => ({
    key,
    ...GROUP_META.value[key],
    items: byGroup.get(key)!,
  }));
});

const emptyState = computed(() => {
  if (activeTab.value === "all") {
    return {
      icon: LucideInbox,
      title: viewUser.value
        ? __("Nothing assigned to {0} right now", viewName.value)
        : __("Nothing assigned to you right now"),
      message: authStore.canSeeOverview
        ? __(
            "Pick a team member above to see their work, or open the Team page for everyone."
          )
        : __(
            "Tasks and tickets assigned to you will show up here, most urgent first."
          ),
    };
  }
  const messages: Record<Exclude<Tab, "all" | "done">, string> = {
    overdue: __("Nothing is overdue. Nice work."),
    at_risk: __("Nothing looks likely to slip right now."),
    key: __("None of this work is marked as key."),
    task: __("No open tasks are assigned here."),
    ticket: __("No open tickets are assigned here."),
  };
  return {
    icon: LucideCircleCheck,
    title: __("Nothing here"),
    message: messages[activeTab.value as Exclude<Tab, "all" | "done">],
  };
});

// --- steps on a task ---

// the item whose button shows a spinner while its step loads
const busy = ref<string | null>(null);

const detailTask = ref<TaskRef | null>(null);
const detailAction = ref<TaskAction | null>(null);

// the dialog closes itself once a step has loaded, so the spinner can stop
watch(detailTask, (task) => {
  if (task) return;
  detailAction.value = null;
  busy.value = null;
});

const start = createResource({
  url: "helpdesk.tasky.api.update_task_status",
  onSuccess() {
    toast.success(__("Started"));
    busy.value = null;
    work.reload();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't start the task.")));
    busy.value = null;
  },
});

const { approve } = useApproveTask(() => {
  busy.value = null;
  work.reload();
});

function openTask(item: WorkItem, action: TaskAction | null) {
  detailAction.value = action;
  detailTask.value = {
    name: item.name,
    subject: item.title,
    project: item.project,
    project_name: item.project_name,
  };
}

function onStep(step: WorkStep, item: WorkItem) {
  if (step === "details") return openTask(item, null);
  busy.value = item.name;
  if (step === "start")
    return start.submit({ task: item.name, status: "Working" });
  if (step === "approve") {
    // another approval is already running; don't leave this row spinning
    if (!approve({ name: item.name })) busy.value = null;
    return;
  }
  // these dialogs need the whole task (timer, hold, dependency), so load it first
  openTask(item, step);
}
</script>
