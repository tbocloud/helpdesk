<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Team") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="refreshing"
          :aria-label="__('Refresh')"
          @click="refresh"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Who is working on what across your projects, what's due this week, and who has room for more."
            )
          }}
        </p>

        <div
          class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"
        >
          <!-- View switch -->
          <div class="max-w-full self-start overflow-x-auto lg:self-auto">
            <TabButtons
              :model-value="view"
              size="md"
              :aria-label="__('Show the team')"
              :options="
                VIEWS.map((o) => ({
                  label: o.label,
                  value: o.key,
                  iconLeft: o.icon,
                }))
              "
              @update:model-value="setView($event as View)"
            />
          </div>

          <!-- Filters -->
          <div
            v-if="view === 'person'"
            class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:w-[30rem]"
            role="group"
            :aria-label="__('Filter team')"
          >
            <Link
              v-model="filters.project"
              doctype="Project"
              :label="__('Project')"
              :placeholder="__('All projects')"
            />
            <Link
              v-model="filters.customer"
              doctype="HD Customer"
              :label="__('Customer')"
              :placeholder="__('All customers')"
            />
          </div>
        </div>
        <div
          v-if="view === 'person' && hasFilters"
          class="mt-2 flex justify-end"
        >
          <Button variant="ghost" :label="__('Clear filters')" @click="clear">
            <template #prefix>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>

        <ProjectPortfolio
          v-if="view === 'project'"
          ref="portfolioView"
          class="mt-5"
        />

        <CapacityPlanner
          v-else-if="view === 'capacity'"
          ref="capacityView"
          class="mt-5"
        />

        <TaskyState
          v-else-if="workload.error && !workload.data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the team')"
          :message="__('Check your connection and try again.')"
          error
        >
          <Button :label="__('Retry')" @click="workload.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Summary: each tile narrows the people below to those it counts -->
          <div
            class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
            role="group"
            :aria-label="__('Show people')"
          >
            <StatTile
              v-for="tile in tiles"
              :key="tile.key"
              :label="tile.label"
              :value="tile.value"
              :sub="tile.sub"
              :icon="tile.icon"
              :icon-tone="tile.tone"
              :value-tone="tile.tone && tile.value ? tile.tone : 'neutral'"
              :loading="isLoading"
              :pressed="show === tile.key"
              :aria-controls="tableId"
              @click="setShow(tile.key)"
            />
          </div>

          <!-- People -->
          <SectionCard
            :id="tableId"
            :title="showTile?.key ? showTile.label : __('People')"
            :count="isLoading ? undefined : people.length"
            class="mt-6 overflow-hidden"
            :aria-busy="workload.loading"
          >
            <template #actions>
              <FormControl
                v-model="sort"
                type="select"
                class="w-48"
                :options="SORTS"
                :aria-label="__('Sort people')"
              />
            </template>

            <div
              class="hidden gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 xl:grid"
              :class="GRID"
              aria-hidden="true"
            >
              <span>{{ __("Person") }}</span>
              <span>{{ __("Working on") }}</span>
              <span>{{ __("Open work") }}</span>
              <span class="text-right">{{ __("Due this week") }}</span>
              <span class="text-right">{{ __("Done this week") }}</span>
              <span class="text-right">{{ __("Tickets") }}</span>
              <span class="text-right">{{ __("Next due") }}</span>
              <span />
            </div>

            <div v-if="isLoading" :aria-label="__('Loading')">
              <div
                v-for="i in 6"
                :key="i"
                class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
              >
                <div
                  class="size-8 shrink-0 animate-pulse rounded-full bg-surface-gray-2"
                />
                <div class="flex flex-1 flex-col gap-2">
                  <div
                    class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-3 w-2/5 animate-pulse rounded bg-surface-gray-2"
                  />
                </div>
                <div
                  class="hidden h-5 w-24 animate-pulse rounded bg-surface-gray-2 md:block"
                />
                <div
                  class="hidden h-3 w-20 animate-pulse rounded bg-surface-gray-2 md:block"
                />
              </div>
            </div>

            <TaskyState
              v-else-if="!everyone.length"
              :icon="LucideUsers"
              :title="__('No one on your projects yet')"
              :message="
                hasFilters
                  ? __('No one works on the projects these filters match.')
                  : __(
                      'People on the projects you manage or lead will show up here.'
                    )
              "
            >
              <Button
                v-if="hasFilters"
                :label="__('Clear filters')"
                @click="clear"
              />
            </TaskyState>

            <TaskyState
              v-else-if="!people.length"
              :icon="LucideUsers"
              :title="__('No one here right now')"
              :message="showTile?.empty"
            >
              <Button :label="__('Show everyone')" @click="setShow('')" />
            </TaskyState>

            <ul v-else role="list">
              <li
                v-for="person in people"
                :key="person.user"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <!-- the whole row opens the person's work -->
                <RouterLink
                  :to="{ name: 'MyWork', query: { user: person.user } }"
                  class="flex flex-col gap-2.5 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 xl:grid xl:items-center xl:gap-3"
                  :class="GRID"
                  :aria-label="__('Open the work of {0}', person.full_name)"
                >
                  <!-- Person -->
                  <div class="flex min-w-0 items-center gap-3">
                    <UserAvatar :name="person.user" size="lg" />
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-base text-ink-gray-9">
                        {{ person.full_name }}
                      </div>
                      <div class="truncate font-mono text-xs text-ink-gray-5">
                        {{ person.user }}
                      </div>
                      <TaskyBadge
                        v-if="leaveLabel(person.user)"
                        class="mt-1"
                        tone="info"
                        :icon="LucideTreePalm"
                        :label="leaveLabel(person.user)"
                      />
                    </div>
                    <LucideChevronRight
                      class="size-4 shrink-0 text-ink-gray-4 xl:hidden"
                      aria-hidden="true"
                    />
                  </div>

                  <!-- Working on -->
                  <div class="min-w-0">
                    <TaskyBadge
                      v-if="isFree(person) && !leaveLabel(person.user)"
                      tone="success"
                      :icon="LucideCoffee"
                      :label="__('Free')"
                    />
                    <div
                      v-else-if="person.working_on.length"
                      class="flex min-w-0 items-center gap-1.5"
                    >
                      <LucideCircleDot
                        class="size-3.5 shrink-0 text-ink-gray-6"
                        aria-hidden="true"
                      />
                      <span class="sr-only">{{ __("Working on") }}</span>
                      <span
                        class="truncate text-sm text-ink-gray-8"
                        :title="workingOnTitle(person)"
                      >
                        {{ person.working_on[0].title }}
                      </span>
                      <TaskyBadge
                        v-if="person.working_on.length > 1"
                        class="font-mono tabular-nums"
                        :title="workingOnTitle(person)"
                      >
                        +{{ person.working_on.length - 1 }}
                      </TaskyBadge>
                    </div>
                    <span v-else class="text-sm text-ink-gray-5">
                      {{ __("Nothing in progress") }}
                    </span>
                  </div>

                  <!-- Open work -->
                  <div class="flex flex-wrap items-center gap-1.5">
                    <TaskyBadge>
                      <span class="font-mono tabular-nums">{{
                        person.open
                      }}</span>
                      {{ __("open") }}
                    </TaskyBadge>
                    <TaskyBadge
                      v-if="person.review"
                      tone="info"
                      :icon="LucideEye"
                    >
                      <span class="font-mono tabular-nums">{{
                        person.review
                      }}</span>
                      {{ __("review") }}
                    </TaskyBadge>
                    <TaskyBadge
                      v-if="person.on_hold"
                      tone="warning"
                      :icon="LucidePause"
                    >
                      <span class="font-mono tabular-nums">{{
                        person.on_hold
                      }}</span>
                      {{ __("on hold") }}
                    </TaskyBadge>
                    <TaskyBadge
                      v-if="person.overdue"
                      tone="danger"
                      :icon="LucideAlarmClock"
                    >
                      <span class="font-mono tabular-nums">{{
                        person.overdue
                      }}</span>
                      {{ __("overdue") }}
                    </TaskyBadge>
                    <span
                      v-if="person.estimated_hours"
                      class="font-mono text-xs tabular-nums text-ink-gray-5"
                      :title="__('Estimated hours of open tasks')"
                    >
                      ~{{ person.estimated_hours }}h
                      <span class="sr-only">{{ __("estimated") }}</span>
                    </span>
                  </div>

                  <!-- This week, tickets: one labelled line below xl, columns above -->
                  <div class="flex flex-wrap gap-x-4 gap-y-1.5 xl:contents">
                    <div
                      class="flex items-center gap-1.5 text-sm xl:justify-end"
                      :class="
                        person.due_this_week
                          ? 'text-ink-gray-8'
                          : 'text-ink-gray-5'
                      "
                    >
                      <span class="text-ink-gray-5 xl:sr-only">{{
                        __("Due this week")
                      }}</span>
                      <span class="font-mono tabular-nums">{{
                        person.due_this_week
                      }}</span>
                    </div>
                    <div
                      class="flex items-center gap-1.5 text-sm xl:justify-end"
                      :class="
                        person.done_this_week
                          ? 'text-ink-gray-8'
                          : 'text-ink-gray-5'
                      "
                    >
                      <span class="text-ink-gray-5 xl:sr-only">{{
                        __("Done this week")
                      }}</span>
                      <span class="font-mono tabular-nums">{{
                        person.done_this_week
                      }}</span>
                    </div>
                    <div
                      class="flex flex-wrap items-center gap-1.5 text-sm xl:justify-end"
                      :class="
                        person.tickets ? 'text-ink-gray-8' : 'text-ink-gray-5'
                      "
                    >
                      <span class="text-ink-gray-5 xl:sr-only">{{
                        __("Tickets")
                      }}</span>
                      <span class="font-mono tabular-nums">{{
                        person.tickets
                      }}</span>
                      <TaskyBadge
                        v-if="person.sla_breached"
                        tone="danger"
                        :icon="LucideAlarmClock"
                      >
                        <span class="font-mono tabular-nums">{{
                          person.sla_breached
                        }}</span>
                        {{ __("SLA breached") }}
                      </TaskyBadge>
                    </div>
                  </div>

                  <!-- Next due -->
                  <div
                    class="min-w-0"
                    :class="person.next_due ? '' : 'hidden xl:block'"
                  >
                    <div
                      v-if="person.next_due"
                      class="flex min-w-0 flex-wrap items-center gap-x-1.5 xl:block xl:text-right"
                    >
                      <span class="text-sm text-ink-gray-5 xl:sr-only">{{
                        __("Next due")
                      }}</span>
                      <div
                        class="min-w-0 max-w-full truncate text-sm text-ink-gray-8"
                        :title="person.next_due.title"
                      >
                        {{ person.next_due.title }}
                      </div>
                      <div
                        class="flex items-center gap-1 font-mono text-xs tabular-nums xl:justify-end"
                        :class="
                          isPast(person.next_due.deadline)
                            ? 'font-medium text-danger'
                            : 'text-ink-gray-5'
                        "
                      >
                        <LucideAlarmClock
                          v-if="isPast(person.next_due.deadline)"
                          class="size-3.5"
                          aria-hidden="true"
                        />
                        {{ formatDate(person.next_due.deadline) }}
                        <span
                          v-if="isPast(person.next_due.deadline)"
                          class="font-sans"
                          >· {{ __("Overdue") }}</span
                        >
                      </div>
                    </div>
                    <span v-else class="text-sm text-ink-gray-5">
                      {{ __("No due date") }}
                    </span>
                  </div>

                  <LucideChevronRight
                    class="hidden size-4 text-ink-gray-4 xl:block"
                    aria-hidden="true"
                  />
                </RouterLink>
              </li>
            </ul>
          </SectionCard>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Tone } from "@/components/tone";
import { Link, UserAvatar } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch, type Component } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCoffee from "~icons/lucide/coffee";
import LucideEye from "~icons/lucide/eye";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideGauge from "~icons/lucide/gauge";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTreePalm from "~icons/lucide/tree-palm";
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
import { useOnLeave } from "@/composables/onLeave";
import CapacityPlanner from "./components/CapacityPlanner.vue";
import ProjectPortfolio from "./components/ProjectPortfolio.vue";

interface TaskRef {
  name: string;
  title: string;
}

interface Person {
  user: string;
  full_name: string;
  working_on: (TaskRef & { project_name: string | null })[];
  next_due: (TaskRef & { deadline: string }) | null;
  open: number;
  working: number;
  review: number;
  on_hold: number;
  overdue: number;
  due_this_week: number;
  done_this_week: number;
  tickets: number;
  sla_breached: number;
  estimated_hours: number;
}

interface Totals {
  people: number;
  working_now: number;
  free: number;
  open: number;
  overdue: number;
  review: number;
  done_this_week: number;
}

interface TeamWorkload {
  people: Person[];
  totals: Totals;
}

/** Which people the table shows: everyone, or those a summary tile counts. */
type Show = "" | "working" | "free" | "overdue" | "review" | "done";
const SHOWS: Show[] = ["", "working", "free", "overdue", "review", "done"];

const SHOW_TEST: Record<Exclude<Show, "">, (p: Person) => boolean> = {
  working: (p) => p.working > 0,
  free: (p) => isFree(p),
  overdue: (p) => p.overdue > 0,
  review: (p) => p.review > 0,
  done: (p) => p.done_this_week > 0,
};

type Sort = "overdue" | "open" | "due_week" | "next_due" | "name";

const SORTS: { label: string; value: Sort }[] = [
  { label: __("Most overdue first"), value: "overdue" },
  { label: __("Most open work first"), value: "open" },
  { label: __("Most due this week"), value: "due_week" },
  { label: __("Next due date"), value: "next_due" },
  { label: __("Name"), value: "name" },
];

const byName = (a: Person, b: Person) => a.full_name.localeCompare(b.full_name);
const NO_DATE = "9999-12-31";

// "overdue" is the server's own order: most overdue, then most open work
const SORT_COMPARE: Record<
  Exclude<Sort, "overdue">,
  (a: Person, b: Person) => number
> = {
  open: (a, b) => b.open - a.open || byName(a, b),
  due_week: (a, b) => b.due_this_week - a.due_this_week || byName(a, b),
  next_due: (a, b) =>
    (a.next_due?.deadline ?? NO_DATE).localeCompare(
      b.next_due?.deadline ?? NO_DATE
    ) || byName(a, b),
  name: byName,
};

const GRID =
  "xl:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_minmax(0,10rem)_4.5rem_4.5rem_minmax(0,7rem)_minmax(0,9rem)_1rem]";

const route = useRoute();
const router = useRouter();
const { leaveLabel } = useOnLeave();
const tableId = `team-people-${useId()}`;

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

type View = "person" | "project" | "capacity";

const VIEWS: { key: View; label: string; icon: Component }[] = [
  { key: "person", label: __("By person"), icon: LucideUsers },
  { key: "project", label: __("By project"), icon: LucideFolderKanban },
  { key: "capacity", label: __("Capacity"), icon: LucideGauge },
];

const view = computed<View>(() => {
  const value = queryValue("view") as View;
  return VIEWS.some((v) => v.key === value) ? value : "person";
});

function setView(next: View) {
  router.replace({
    query: { ...route.query, view: next === "person" ? undefined : next },
  });
}

// the table's narrowing and order live in the URL too, so a view can be shared
const show = computed<Show>(() => {
  const value = queryValue("show") as Show;
  return SHOWS.includes(value) ? value : "";
});

function setShow(next: Show) {
  const value = show.value === next ? "" : next;
  router.replace({ query: { ...route.query, show: value || undefined } });
}

const sort = computed<Sort>({
  get: () => {
    const value = queryValue("sort") as Sort;
    return SORTS.some((s) => s.value === value) ? value : "overdue";
  },
  set: (value) =>
    router.replace({
      query: {
        ...route.query,
        sort: value === "overdue" ? undefined : value,
      },
    }),
});

const portfolioView = ref<InstanceType<typeof ProjectPortfolio> | null>(null);
const capacityView = ref<InstanceType<typeof CapacityPlanner> | null>(null);

// the other views load their own data
const otherView = computed(() =>
  view.value === "project"
    ? portfolioView.value
    : view.value === "capacity"
    ? capacityView.value
    : null
);

const refreshing = computed(() =>
  view.value === "person" ? workload.loading : !!otherView.value?.loading
);

function refresh() {
  if (view.value === "person") workload.reload();
  else otherView.value?.reload();
}

const filters = reactive({
  project: queryValue("project"),
  customer: queryValue("customer"),
});

const hasFilters = computed(() => !!(filters.project || filters.customer));

function clear() {
  filters.project = "";
  filters.customer = "";
}

const workload = createResource({
  url: "helpdesk.api.work.get_team_workload",
  makeParams: () => ({
    project: filters.project || null,
    customer: filters.customer || null,
  }),
  auto: view.value === "person",
});

// keep the filters in the URL so the view can be shared
watch(
  () => ({ ...filters }),
  (f) => {
    if (view.value !== "person") return;
    router.replace({
      query: {
        ...route.query,
        project: f.project || undefined,
        customer: f.customer || undefined,
      },
    });
    workload.reload();
  },
  { deep: true }
);

// the project view may have changed the customer in the URL meanwhile
watch(view, (next) => {
  if (next !== "person") return;
  const project = queryValue("project");
  const customer = queryValue("customer");
  if (project === filters.project && customer === filters.customer) {
    if (!workload.data) workload.reload();
    return;
  }
  filters.project = project;
  filters.customer = customer;
});

const data = computed(() => workload.data as TeamWorkload | undefined);
const isLoading = computed(() => workload.loading && !data.value);
const everyone = computed<Person[]>(() => data.value?.people ?? []);

const people = computed<Person[]>(() => {
  const test = show.value ? SHOW_TEST[show.value] : null;
  const shown = test ? everyone.value.filter(test) : [...everyone.value];
  return sort.value === "overdue"
    ? shown
    : shown.sort(SORT_COMPARE[sort.value]);
});

interface Tile {
  key: Show;
  label: string;
  value: number;
  sub?: string;
  icon: Component;
  tone?: Tone;
  /** shown when the tile narrows the table to no one */
  empty: string;
}

const tiles = computed<Tile[]>(() => {
  const t = data.value?.totals;
  const total = t?.people ?? 0;
  const ofTeam = (n: number) =>
    total ? __("{0}% of team", String(Math.round((n / total) * 100))) : "";
  const peopleWith = (key: "overdue" | "review") => {
    const n = everyone.value.filter(SHOW_TEST[key]).length;
    return n === 1 ? __("1 person") : __("{0} people", String(n));
  };
  return [
    {
      key: "",
      label: __("People"),
      icon: LucideUsers,
      value: total,
      empty: "",
    },
    {
      key: "working",
      label: __("Working now"),
      icon: LucideCircleDot,
      value: t?.working_now ?? 0,
      sub: ofTeam(t?.working_now ?? 0),
      empty: __("No one has a task in progress."),
    },
    {
      key: "free",
      label: __("Free"),
      icon: LucideCoffee,
      value: t?.free ?? 0,
      sub: ofTeam(t?.free ?? 0),
      empty: __("Everyone has open tasks or tickets."),
    },
    {
      key: "overdue",
      label: __("Overdue"),
      icon: LucideAlarmClock,
      value: t?.overdue ?? 0,
      sub: peopleWith("overdue"),
      tone: "danger",
      empty: __("No one has overdue tasks."),
    },
    {
      key: "review",
      label: __("Waiting review"),
      icon: LucideEye,
      value: t?.review ?? 0,
      sub: peopleWith("review"),
      empty: __("No one has tasks waiting for review."),
    },
    {
      key: "done",
      label: __("Done this week"),
      icon: LucideCircleCheck,
      value: t?.done_this_week ?? 0,
      sub: __("Last 7 days"),
      tone: "success",
      empty: __("No one finished a task in the last 7 days."),
    },
  ];
});

const showTile = computed(() => tiles.value.find((t) => t.key === show.value));

function isFree(person: Person) {
  return !person.open && !person.tickets;
}

function workingOnTitle(person: Person) {
  return person.working_on
    .map((t) => (t.project_name ? `${t.title} (${t.project_name})` : t.title))
    .join("\n");
}

function isPast(date: string) {
  return dayjs(date).isBefore(dayjs().startOf("day"));
}

function formatDate(date: string) {
  return dayjs(date).format("D MMM YYYY");
}
</script>
