<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Team") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="workload.loading"
          :aria-label="__('Refresh')"
          @click="workload.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <!-- Filters -->
        <div
          class="grid grid-cols-1 gap-3 sm:grid-cols-2"
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
        <div v-if="hasFilters" class="mt-2 flex justify-end">
          <Button variant="ghost" :label="__('Clear filters')" @click="clear">
            <template #prefix>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>

        <TaskyState
          v-if="workload.error && !workload.data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the team')"
          :message="__('Check your connection and try again.')"
          error
        >
          <Button :label="__('Retry')" @click="workload.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Summary -->
          <div
            class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
          >
            <div
              v-for="tile in tiles"
              :key="tile.key"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm text-ink-gray-6">{{ tile.label }}</span>
                <component
                  :is="tile.icon"
                  class="size-4 shrink-0"
                  :class="tile.tone ? TONE_TEXT[tile.tone] : 'text-ink-gray-5'"
                  aria-hidden="true"
                />
              </div>
              <span
                class="font-mono text-2xl-semibold tabular-nums"
                :class="
                  tile.tone && tile.value > 0
                    ? TONE_TEXT[tile.tone]
                    : 'text-ink-gray-9'
                "
              >
                <span
                  v-if="isLoading"
                  class="inline-block h-7 w-8 animate-pulse rounded bg-surface-gray-2"
                />
                <template v-else>{{ tile.value }}</template>
              </span>
            </div>
          </div>

          <!-- People -->
          <div class="mt-6 flex items-center justify-between gap-2">
            <h2 class="text-base-medium text-ink-gray-8">
              {{ __("People") }}
            </h2>
            <span class="text-sm text-ink-gray-5">
              {{ __("Most overdue first") }}
            </span>
          </div>
          <div
            class="mt-2 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
            :aria-busy="workload.loading"
          >
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
              v-else-if="!people.length"
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

            <ul v-else role="list">
              <li
                v-for="person in people"
                :key="person.user"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <!-- clicking a person lists all their open tasks right here -->
                <component
                  :is="isFree(person) ? 'div' : 'button'"
                  v-bind="
                    isFree(person)
                      ? {}
                      : {
                          type: 'button',
                          'aria-expanded': isExpanded(person),
                          onClick: () => toggle(person),
                        }
                  "
                  class="flex w-full flex-col gap-2.5 px-4 py-3 text-left transition-colors focus-visible:outline-none xl:grid xl:items-center xl:gap-3"
                  :class="[
                    GRID,
                    isFree(person)
                      ? ''
                      : 'hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1',
                  ]"
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
                    </div>
                  </div>

                  <!-- Working on -->
                  <div class="min-w-0">
                    <TaskyBadge
                      v-if="isFree(person)"
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
                </component>
                <div
                  v-if="isExpanded(person)"
                  class="border-t border-outline-gray-1 bg-surface-gray-1"
                >
                  <ul
                    v-if="person.tasks.length"
                    role="list"
                    :aria-label="__('Open tasks of {0}', person.full_name)"
                  >
                    <li
                      v-for="task in person.tasks"
                      :key="task.name"
                      class="border-b border-outline-gray-1 last:border-b-0"
                    >
                      <WorkItemRow :item="task" />
                    </li>
                  </ul>
                  <p v-else class="px-4 py-3 text-sm text-ink-gray-5">
                    {{ __("No open tasks; only tickets.") }}
                  </p>
                  <div class="flex justify-end px-4 py-2">
                    <RouterLink
                      :to="personRoute(person)"
                      class="text-sm text-ink-gray-7 underline-offset-2 hover:underline focus-visible:underline"
                    >
                      {{ __("Open in Overview") }}
                    </RouterLink>
                  </div>
                </div>
              </li>
            </ul>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link, UserAvatar } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/pages/tasky/components/TaskyBadge.vue";
import TaskyState from "@/pages/tasky/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, reactive, watch, type Component } from "vue";
import {
  RouterLink,
  useRoute,
  useRouter,
  type RouteLocationRaw,
} from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCoffee from "~icons/lucide/coffee";
import LucideEye from "~icons/lucide/eye";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
import WorkItemRow from "./components/WorkItemRow.vue";
import type { WorkItem } from "./workMeta";

interface TaskRef {
  name: string;
  title: string;
}

interface Person {
  user: string;
  full_name: string;
  tasks: WorkItem[];
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

type Tone = "danger" | "info" | "success";

// Full class strings so Tailwind's scanner picks them up.
const TONE_TEXT: Record<Tone, string> = {
  danger: "text-danger",
  info: "text-info",
  success: "text-success",
};

const GRID =
  "xl:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_minmax(0,10rem)_4.5rem_4.5rem_minmax(0,7rem)_minmax(0,9rem)]";

const route = useRoute();
const router = useRouter();

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
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
  auto: true,
});

// keep the filters in the URL so the view can be shared
watch(
  () => ({ ...filters }),
  (f) => {
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

const data = computed(() => workload.data as TeamWorkload | undefined);
const isLoading = computed(() => workload.loading && !data.value);
const people = computed<Person[]>(() => data.value?.people ?? []);

const tiles = computed<
  { key: string; label: string; icon: Component; value: number; tone?: Tone }[]
>(() => {
  const t = data.value?.totals;
  return [
    {
      key: "people",
      label: __("People"),
      icon: LucideUsers,
      value: t?.people ?? 0,
    },
    {
      key: "working_now",
      label: __("Working now"),
      icon: LucideCircleDot,
      value: t?.working_now ?? 0,
    },
    {
      key: "free",
      label: __("Free"),
      icon: LucideCoffee,
      value: t?.free ?? 0,
    },
    {
      key: "overdue",
      label: __("Overdue"),
      icon: LucideAlarmClock,
      value: t?.overdue ?? 0,
      tone: "danger",
    },
    {
      key: "review",
      label: __("Waiting review"),
      icon: LucideEye,
      value: t?.review ?? 0,
      tone: "info",
    },
    {
      key: "done_this_week",
      label: __("Done this week"),
      icon: LucideCircleCheck,
      value: t?.done_this_week ?? 0,
      tone: "success",
    },
  ];
});

const expanded = reactive(new Set<string>());

function isExpanded(person: Person) {
  return expanded.has(person.user);
}

function toggle(person: Person) {
  if (expanded.has(person.user)) expanded.delete(person.user);
  else expanded.add(person.user);
}

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

// The Overview has no "everything" bucket, so open it on the bucket that
// holds the person's most pressing work.
function personRoute(person: Person): RouteLocationRaw {
  let bucket: string | undefined;
  if (person.overdue || person.sla_breached) bucket = undefined;
  else if (person.review) bucket = "review";
  else if (person.on_hold) bucket = "on_hold";
  else bucket = "due_soon";
  return {
    name: "WorkOverview",
    query: {
      assignee: person.user,
      project: filters.project || undefined,
      customer: filters.customer || undefined,
      bucket,
    },
  };
}
</script>
