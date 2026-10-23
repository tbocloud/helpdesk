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
          :loading="work.loading || given.loading"
          :aria-label="__('Refresh')"
          @click="reload"
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
          <div class="-mx-1 mt-4 overflow-x-auto px-1">
            <TabButtons
              v-model="activeTab"
              size="md"
              :aria-label="__('Filter work')"
              :aria-controls="listId"
              :options="
                tabs.map((t) => ({
                  label: t.label,
                  value: t.key,
                  iconLeft: t.icon,
                }))
              "
            >
              <template #suffix="{ button, checked }">
                <span
                  class="font-mono text-xs tabular-nums"
                  :class="checked ? '' : 'text-ink-gray-5'"
                >
                  <span
                    v-if="
                      button.modelValue === 'assigned'
                        ? givenLoading
                        : isLoading
                    "
                    class="inline-block h-3 w-3 animate-pulse rounded bg-surface-gray-2 align-middle"
                  />
                  <template v-else>{{ countFor(button.modelValue) }}</template>
                </span>
              </template>
            </TabButtons>
          </div>

          <div
            :id="listId"
            class="mt-4"
            :aria-busy="activeTab === 'assigned' ? given.loading : work.loading"
          >
            <!-- Loading -->
            <div
              v-if="activeTab === 'assigned' ? givenLoading : isLoading"
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

            <!-- Tasks the person gave to someone else, by who has them -->
            <template v-else-if="activeTab === 'assigned'">
              <div
                v-if="given.error && !given.data"
                class="rounded-lg border border-outline-gray-2 bg-surface-base"
              >
                <TaskyState
                  :icon="LucideCircleAlert"
                  :title="__('Couldn\'t load the tasks given out')"
                  :message="
                    errorText(
                      given.error,
                      __('Check your connection and try again.')
                    )
                  "
                  error
                >
                  <Button :label="__('Retry')" @click="given.reload()" />
                </TaskyState>
              </div>
              <div
                v-else-if="!givenItems.length"
                class="rounded-lg border border-outline-gray-2 bg-surface-base"
              >
                <TaskyState
                  :icon="LucideInbox"
                  :title="
                    viewUser
                      ? __('{0} hasn\'t assigned any open tasks.', viewName)
                      : __('You haven\'t assigned any open tasks.')
                  "
                  :message="
                    __(
                      'Open tasks given to someone else show up here, grouped by who has them.'
                    )
                  "
                />
              </div>
              <template v-else>
                <div
                  class="mb-4 grid grid-cols-1 items-end gap-3 sm:grid-cols-[repeat(2,minmax(0,16rem))_auto]"
                  role="group"
                  :aria-label="__('Filter the tasks given out')"
                >
                  <Select
                    :model-value="givenFilters.to || undefined"
                    :options="givenPeople"
                    :label="__('Person')"
                    :placeholder="__('Everyone')"
                    @update:model-value="
                      (v: unknown) => (givenFilters.to = (v as string) || '')
                    "
                  />
                  <Select
                    :model-value="givenFilters.project || undefined"
                    :options="givenProjects"
                    :label="__('Project')"
                    :placeholder="__('All projects')"
                    @update:model-value="
                      (v: unknown) =>
                        (givenFilters.project = (v as string) || '')
                    "
                  />
                  <Button
                    v-if="givenFilters.to || givenFilters.project"
                    variant="ghost"
                    class="justify-self-start"
                    :label="__('Clear filters')"
                    @click="clearGivenFilters"
                  >
                    <template #prefix>
                      <LucideX class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </div>
                <div
                  v-if="!givenGroups.length"
                  class="rounded-lg border border-outline-gray-2 bg-surface-base"
                >
                  <TaskyState
                    :icon="LucideCircleCheck"
                    :title="__('Nothing matches these filters')"
                    :message="__('Pick another person or project.')"
                  >
                    <Button
                      :label="__('Clear filters')"
                      @click="clearGivenFilters"
                    />
                  </TaskyState>
                </div>
                <div v-else class="flex flex-col gap-4">
                  <SectionCard
                    v-for="group in givenGroups"
                    :key="group.user"
                    :title="group.name"
                    :count="group.items.length"
                    class="overflow-hidden"
                  >
                    <ul role="list">
                      <li
                        v-for="item in group.items"
                        :key="itemKey(item)"
                        class="border-b border-outline-gray-1 last:border-b-0"
                      >
                        <WorkItemRow
                          :item="item"
                          show-assignees
                          opens
                          @open="openTask(item, null, false)"
                        >
                          <template #actions>
                            <WorkItemActions
                              :item="item"
                              :mine="false"
                              :busy="busy === item.name"
                              @step="(step, i) => onStep(step, i, false)"
                            />
                          </template>
                        </WorkItemRow>
                      </li>
                    </ul>
                  </SectionCard>
                </div>
              </template>
            </template>

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
                    <!-- a task opens its details here, which also clears its New mark -->
                    <WorkItemRow
                      :item="item"
                      :opens="item.kind === 'task'"
                      @open="openTask(item, null)"
                    >
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
      :mine="detailMine"
      @changed="reload"
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
  Select,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch, type Component } from "vue";
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
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
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

type Tab =
  | "all"
  | "overdue"
  | "at_risk"
  | "key"
  | "task"
  | "ticket"
  | "assigned"
  | "done";

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

// open tasks this person gave to someone else (Assigned by me)
const given = createResource({
  url: "helpdesk.api.work.get_assigned_by",
  makeParams: () => ({ user: viewUser.value || undefined }),
  auto: true,
});

const givenLoading = computed(() => given.loading && !given.data);

function reload() {
  work.reload();
  given.reload();
}

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
  // another person gave out other tasks, so their filters start empty
  Object.assign(givenFilters, { to: "", project: "" });
  router.replace({
    query: {
      ...route.query,
      user: user || undefined,
      to: undefined,
      project: undefined,
    },
  });
  reload();
});

const tabs = computed<{ key: Tab; label: string; icon?: Component }[]>(() => [
  { key: "all", label: __("All") },
  { key: "overdue", label: __("Overdue"), icon: LucideAlarmClock },
  { key: "at_risk", label: __("At risk"), icon: LucideTriangleAlert },
  { key: "key", label: __("Key"), icon: LucideStar },
  { key: "task", label: __("Tasks") },
  { key: "ticket", label: __("Tickets") },
  {
    key: "assigned",
    label: viewUser.value ? __("Assigned by them") : __("Assigned by me"),
    icon: LucideUsers,
  },
  { key: "done", label: __("Completed"), icon: LucideCircleCheck },
]);

const TAB_KEYS: Tab[] = [
  "all",
  "overdue",
  "at_risk",
  "key",
  "task",
  "ticket",
  "assigned",
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

// tasks opened since the list loaded; the server stops marking them on the next load
const opened = ref(new Set<string>());

const items = computed<WorkItem[]>(() =>
  ((work.data as MyWork | undefined)?.items ?? []).map((item) =>
    item.assignment_state && opened.value.has(item.name)
      ? { ...item, assignment_state: null }
      : item
  )
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
  if (tab === "assigned") return givenItems.value.length;
  return items.value.filter((i) => matches(i, tab)).length;
}

function doneRoute(item: DoneItem) {
  if (item.kind === "ticket")
    return { name: "TicketAgent", params: { ticketId: item.name } };
  if (item.project)
    return { name: "TaskyProject", params: { projectId: item.project } };
  return null;
}

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const givenItems = computed<WorkItem[]>(
  () => (given.data as { items: WorkItem[] } | undefined)?.items ?? []
);

// Person and Project live in the URL with the tab, so a view can be shared
const givenFilters = reactive({
  to: queryValue("to"),
  project: queryValue("project"),
});

watch(
  () => ({ ...givenFilters }),
  (f) =>
    router.replace({
      query: {
        ...route.query,
        to: f.to || undefined,
        project: f.project || undefined,
      },
    })
);

function clearGivenFilters() {
  Object.assign(givenFilters, { to: "", project: "" });
}

function personName(user: string) {
  return userStore.getUser(user)?.full_name || user;
}

const givenPeople = computed(() =>
  [...new Set(givenItems.value.flatMap((i) => i.given_to ?? []))]
    .map((user) => ({ label: personName(user), value: user }))
    .sort((a, b) => a.label.localeCompare(b.label))
);

const givenProjects = computed(() => {
  const projects = new Map<string, string>();
  for (const item of givenItems.value)
    if (item.project)
      projects.set(item.project, item.project_name || item.project);
  return [...projects]
    .map(([value, label]) => ({ label, value }))
    .sort((a, b) => a.label.localeCompare(b.label));
});

/** One group per person the tasks were given to, the busiest first. */
const givenGroups = computed(() => {
  const byPerson = new Map<string, WorkItem[]>();
  for (const item of givenItems.value) {
    if (givenFilters.project && item.project !== givenFilters.project) continue;
    for (const user of item.given_to ?? []) {
      if (givenFilters.to && user !== givenFilters.to) continue;
      if (!byPerson.has(user)) byPerson.set(user, []);
      byPerson.get(user)!.push(item);
    }
  }
  return [...byPerson]
    .map(([user, items]) => ({ user, name: personName(user), items }))
    .sort(
      (a, b) => b.items.length - a.items.length || a.name.localeCompare(b.name)
    );
});

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
  const messages: Record<Exclude<Tab, "all" | "done" | "assigned">, string> = {
    overdue: __("Nothing is overdue. Nice work."),
    at_risk: __("Nothing looks likely to slip right now."),
    key: __("None of this work is marked as key."),
    task: __("No open tasks are assigned here."),
    ticket: __("No open tickets are assigned here."),
  };
  return {
    icon: LucideCircleCheck,
    title: __("Nothing here"),
    message:
      messages[activeTab.value as Exclude<Tab, "all" | "done" | "assigned">],
  };
});

// --- steps on a task ---

// the item whose button shows a spinner while its step loads
const busy = ref<string | null>(null);

const detailTask = ref<TaskRef | null>(null);
const detailAction = ref<TaskAction | null>(null);
// the open task is the viewer's own (not someone else's work, nor one they gave out)
const detailMine = ref(true);

// the dialog closes itself once a step has loaded, so the spinner can stop
watch(detailTask, (task) => {
  if (task) return;
  detailAction.value = null;
  busy.value = null;
  if (route.query.task)
    router.replace({ query: { ...route.query, task: undefined } });
});

// a notification links here with ?task=<name> to open that task's details
watch(
  () => route.query.task,
  (name) => {
    if (typeof name !== "string" || !name || detailTask.value?.name === name)
      return;
    detailAction.value = null;
    detailMine.value = !viewUser.value;
    opened.value.add(name);
    detailTask.value = { name };
  },
  { immediate: true }
);

const start = createResource({
  url: "helpdesk.tasky.api.update_task_status",
  onSuccess() {
    toast.success(__("Started"));
    busy.value = null;
    reload();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't start the task.")));
    busy.value = null;
  },
});

const { approve } = useApproveTask(() => {
  busy.value = null;
  reload();
});

function openTask(
  item: WorkItem,
  action: TaskAction | null,
  assigned = !viewUser.value
) {
  detailAction.value = action;
  detailMine.value = assigned;
  // only the assignee's own open marks it seen (TaskDetailDialog)
  if (assigned) opened.value.add(item.name);
  detailTask.value = {
    name: item.name,
    subject: item.title,
    project: item.project,
    project_name: item.project_name,
  };
}

function onStep(step: WorkStep, item: WorkItem, assigned = !viewUser.value) {
  if (step === "details") return openTask(item, null, assigned);
  busy.value = item.name;
  if (step === "start")
    return start.submit({ task: item.name, status: "Working" });
  if (step === "approve") {
    // another approval is already running; don't leave this row spinning
    if (!approve({ name: item.name })) busy.value = null;
    return;
  }
  // these dialogs need the whole task (timer, hold, dependency), so load it first
  openTask(item, step, assigned);
}
</script>
