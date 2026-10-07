<template>
  <div>
    <!-- Filters -->
    <div
      class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"
      role="group"
      :aria-label="__('Filter projects')"
    >
      <div
        class="flex gap-1 self-start"
        role="radiogroup"
        :aria-label="__('Project status')"
      >
        <button
          v-for="option in STATUS_OPTIONS"
          :key="option.key"
          type="button"
          role="radio"
          :aria-checked="filters.status === option.key"
          class="rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :class="
            filters.status === option.key
              ? 'bg-surface-gray-3 text-ink-gray-9'
              : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
          "
          @click="filters.status = option.key"
        >
          {{ option.label }}
        </button>
      </div>
      <div class="w-full sm:w-64">
        <Link
          v-model="filters.customer"
          doctype="HD Customer"
          :label="__('Customer')"
          :placeholder="__('All customers')"
        />
      </div>
    </div>

    <TaskyState
      v-if="portfolio.error && !data"
      class="mt-6"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the projects')"
      :message="__('Check your connection and try again.')"
      error
    >
      <Button :label="__('Retry')" @click="portfolio.reload()" />
    </TaskyState>

    <template v-else>
      <!-- Summary -->
      <div
        class="mt-5 grid grid-cols-2 gap-3"
        :class="tiles.length === 4 ? 'lg:grid-cols-4' : 'lg:grid-cols-3'"
      >
        <StatTile
          v-for="tile in tiles"
          :key="tile.key"
          :label="tile.label"
          :value="tile.value"
          :icon="tile.icon"
          :icon-tone="tile.danger ? 'danger' : 'neutral'"
          :value-tone="tile.danger && tile.value ? 'danger' : 'neutral'"
          :loading="isLoading"
        />
      </div>

      <!-- Projects -->
      <div class="mt-6 flex items-center justify-between gap-2">
        <h2 class="text-base-medium text-ink-gray-8">{{ __("Projects") }}</h2>
        <span v-if="!isLoading" class="text-sm text-ink-gray-5">
          {{ __("Who is on each project, and what they're doing now") }}
        </span>
      </div>

      <div
        v-if="isLoading"
        class="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
        aria-busy="true"
        :aria-label="__('Loading')"
      >
        <div
          v-for="i in 6"
          :key="i"
          class="flex flex-col gap-4 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
        >
          <div class="h-4 w-3/5 animate-pulse rounded bg-surface-gray-2" />
          <div class="h-3 w-2/5 animate-pulse rounded bg-surface-gray-2" />
          <div
            class="h-1.5 w-full animate-pulse rounded-full bg-surface-gray-2"
          />
          <div v-for="j in 3" :key="j" class="flex items-center gap-2">
            <div
              class="size-6 shrink-0 animate-pulse rounded-full bg-surface-gray-2"
            />
            <div class="h-3 flex-1 animate-pulse rounded bg-surface-gray-2" />
          </div>
        </div>
      </div>

      <div
        v-else-if="!projects.length"
        class="mt-2 rounded-lg border border-outline-gray-2 bg-surface-base"
      >
        <TaskyState
          :icon="LucideFolderKanban"
          :title="__('No projects to show')"
          :message="
            filters.customer
              ? __('No projects for this customer match the filters.')
              : filters.status === 'Open'
              ? __(
                  'No open projects. Completed and on-hold ones are under All.'
                )
              : __('Projects you manage or lead will show up here.')
          "
        >
          <Button
            v-if="filters.customer"
            :label="__('Clear customer')"
            @click="filters.customer = ''"
          />
          <Button
            v-else-if="filters.status === 'Open'"
            :label="__('Show all projects')"
            @click="filters.status = 'All'"
          />
        </TaskyState>
      </div>

      <ul
        v-else
        role="list"
        class="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
        :aria-busy="portfolio.loading"
      >
        <li
          v-for="(project, index) in projects"
          :key="project.name"
          class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 transition-colors hover:border-outline-gray-3"
        >
          <!-- Name, customer, type -->
          <div class="min-w-0">
            <div class="flex items-start justify-between gap-2">
              <RouterLink
                :to="boardRoute(project.name)"
                class="min-w-0 truncate rounded text-base-semibold text-ink-gray-9 hover:underline focus-visible:underline focus-visible:outline-none"
                :title="__('Open the board of {0}', project.project_name)"
              >
                {{ project.project_name }}
              </RouterLink>
              <TaskStatusBadge
                v-if="project.status !== 'Open'"
                kind="project"
                :status="project.status"
              />
            </div>
            <div
              class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-gray-6"
            >
              <span
                v-if="project.customer"
                class="flex min-w-0 items-center gap-1"
              >
                <LucideBuilding2 class="size-3.5 shrink-0" aria-hidden="true" />
                <span class="sr-only">{{ __("Customer") }}</span>
                <span class="truncate">{{ project.customer }}</span>
              </span>
              <TaskyBadge
                v-if="project.project_type"
                :label="__(project.project_type)"
              />
            </div>
            <div
              v-if="project.lead"
              class="mt-1 flex min-w-0 items-center gap-1 text-sm text-ink-gray-6"
            >
              <LucideUserStar class="size-3.5 shrink-0" aria-hidden="true" />
              <span class="truncate">{{
                __("Lead: {0}", project.lead_name)
              }}</span>
            </div>
          </div>

          <!-- Progress -->
          <div class="flex flex-col gap-1.5">
            <div class="flex items-center justify-between text-xs">
              <span class="text-ink-gray-5">{{ __("Progress") }}</span>
              <span class="font-mono tabular-nums text-ink-gray-7">
                {{ project.counts.done }}/{{ project.counts.total }}
                <span class="text-ink-gray-5">· {{ project.progress }}%</span>
              </span>
            </div>
            <div
              class="h-1.5 w-full overflow-hidden rounded-full bg-surface-gray-2"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="project.progress"
              :aria-label="
                __(
                  '{0} of {1} tasks done',
                  project.counts.done,
                  project.counts.total
                )
              "
            >
              <div
                class="h-full rounded-full bg-success"
                :style="{ width: project.progress + '%' }"
              />
            </div>
          </div>

          <!-- Counts -->
          <div class="flex flex-wrap items-center gap-1.5">
            <TaskyBadge>
              <span class="font-mono tabular-nums">{{
                project.counts.open
              }}</span>
              {{ __("open") }}
            </TaskyBadge>
            <TaskyBadge v-if="project.counts.working" :icon="LucideCircleDot">
              <span class="font-mono tabular-nums">{{
                project.counts.working
              }}</span>
              {{ __("in progress") }}
            </TaskyBadge>
            <TaskyBadge
              v-if="project.counts.review"
              tone="info"
              :icon="LucideEye"
            >
              <span class="font-mono tabular-nums">{{
                project.counts.review
              }}</span>
              {{ __("review") }}
            </TaskyBadge>
            <TaskyBadge
              v-if="project.counts.on_hold"
              tone="warning"
              :icon="LucidePause"
            >
              <span class="font-mono tabular-nums">{{
                project.counts.on_hold
              }}</span>
              {{ __("on hold") }}
            </TaskyBadge>
            <TaskyBadge
              v-if="project.counts.overdue"
              tone="danger"
              :icon="LucideAlarmClock"
            >
              <span class="font-mono tabular-nums">{{
                project.counts.overdue
              }}</span>
              {{ __("overdue") }}
            </TaskyBadge>
          </div>

          <!-- Next milestone -->
          <div
            v-if="project.next_milestone"
            class="flex min-w-0 items-center gap-1.5 text-sm"
          >
            <LucideFlag
              class="size-3.5 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <span class="sr-only">{{ __("Next milestone") }}</span>
            <span
              class="min-w-0 truncate text-ink-gray-8"
              :title="project.next_milestone.subject"
            >
              {{ project.next_milestone.subject }}
            </span>
            <span
              v-if="project.next_milestone.due"
              class="ml-auto shrink-0 font-mono text-xs tabular-nums"
              :class="
                project.next_milestone.is_overdue
                  ? 'font-medium text-danger'
                  : 'text-ink-gray-5'
              "
            >
              {{ formatDate(project.next_milestone.due) }}
              <span v-if="project.next_milestone.is_overdue" class="font-sans"
                >· {{ __("Overdue") }}</span
              >
            </span>
          </div>

          <!-- Team -->
          <div class="border-t border-outline-gray-1 pt-3">
            <h3 class="mb-1.5 text-xs text-ink-gray-5">
              {{ __("Team") }}
              <span class="font-mono tabular-nums"
                >({{ project.members.length }})</span
              >
            </h3>
            <p v-if="!project.members.length" class="text-sm text-ink-gray-5">
              {{ __("No one on this project yet") }}
            </p>
            <ul
              v-else
              :id="`portfolio-team-${index}`"
              role="list"
              class="-mx-1.5 flex flex-col"
            >
              <li v-for="member in visibleMembers(project)" :key="member.user">
                <RouterLink
                  :to="personRoute(member.user)"
                  class="flex min-w-0 items-center gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  :title="__('Open the work of {0}', member.full_name)"
                >
                  <UserAvatar :name="member.user" size="sm" />
                  <div class="min-w-0 flex-1">
                    <div class="flex min-w-0 items-center gap-1.5">
                      <span class="truncate text-sm text-ink-gray-9">
                        {{ member.full_name }}
                      </span>
                      <span class="shrink-0 text-xs text-ink-gray-5">
                        {{ roleLabel(member) }}
                      </span>
                    </div>
                    <div
                      v-if="member.working_on"
                      class="flex min-w-0 items-center gap-1 text-xs text-ink-gray-7"
                    >
                      <LucideCircleDot
                        class="size-3 shrink-0 text-success"
                        aria-hidden="true"
                      />
                      <span
                        class="truncate"
                        :title="member.working_on.subject"
                        >{{
                          __("Working on {0}", member.working_on.subject)
                        }}</span
                      >
                    </div>
                  </div>
                  <span
                    class="shrink-0 text-xs"
                    :class="member.open ? 'text-ink-gray-7' : 'text-ink-gray-5'"
                  >
                    <template v-if="member.open">
                      <span class="font-mono tabular-nums">{{
                        member.open
                      }}</span>
                      {{ __("open") }}
                    </template>
                    <template v-else>{{ __("No open tasks") }}</template>
                  </span>
                </RouterLink>
              </li>
            </ul>
            <button
              v-if="project.members.length > MEMBER_PREVIEW"
              type="button"
              class="mt-1 rounded text-xs text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :aria-expanded="expanded.has(project.name)"
              :aria-controls="`portfolio-team-${index}`"
              @click="toggleMembers(project.name)"
            >
              {{
                expanded.has(project.name)
                  ? __("Show fewer")
                  : __("Show {0} more", project.members.length - MEMBER_PREVIEW)
              }}
            </button>
          </div>

          <RouterLink
            :to="boardRoute(project.name)"
            class="mt-auto flex items-center gap-1 self-start rounded text-sm text-ink-gray-7 underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none"
          >
            {{ __("Open board") }}
            <LucideArrowRight class="size-3.5" aria-hidden="true" />
          </RouterLink>
        </li>
      </ul>

      <!-- People x projects -->
      <template v-if="isLoading || people.length">
        <div class="mt-8 flex items-center justify-between gap-2">
          <h2 class="text-base-medium text-ink-gray-8">
            {{ __("Who works on what") }}
          </h2>
          <span class="text-sm text-ink-gray-5">{{ __("Busiest first") }}</span>
        </div>
        <div
          class="mt-2 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
        >
          <div
            class="hidden gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
            :class="PEOPLE_GRID"
            aria-hidden="true"
          >
            <span>{{ __("Person") }}</span>
            <span>{{ __("Projects") }}</span>
            <span class="text-right">{{ __("Open tasks") }}</span>
          </div>

          <div v-if="isLoading" :aria-label="__('Loading')">
            <div
              v-for="i in 4"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
            >
              <div
                class="size-6 shrink-0 animate-pulse rounded-full bg-surface-gray-2"
              />
              <div
                class="h-3.5 w-1/5 animate-pulse rounded bg-surface-gray-2"
              />
              <div class="h-5 w-1/3 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <ul v-else role="list">
            <li
              v-for="person in people"
              :key="person.user"
              class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 md:grid md:items-center md:gap-3"
              :class="PEOPLE_GRID"
            >
              <RouterLink
                :to="personRoute(person.user)"
                class="flex min-w-0 items-center gap-2 self-start rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 md:self-auto"
                :title="__('Open the work of {0}', person.full_name)"
              >
                <UserAvatar :name="person.user" size="sm" />
                <span class="truncate text-sm text-ink-gray-9 hover:underline">
                  {{ person.full_name }}
                </span>
              </RouterLink>

              <div class="flex min-w-0 flex-wrap items-center gap-1.5">
                <TaskyBadge
                  v-if="person.is_free"
                  tone="success"
                  :icon="LucideCoffee"
                  :label="__('Free')"
                />
                <template v-else>
                  <RouterLink
                    v-for="p in person.projects"
                    :key="p.project"
                    :to="boardRoute(p.project)"
                    class="inline-flex h-6 max-w-full items-center gap-1.5 rounded-md border border-outline-gray-2 px-2 text-xs text-ink-gray-8 transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    :title="
                      p.working_now
                        ? __('{0}: working on it now', p.project_name)
                        : p.project_name
                    "
                  >
                    <LucideCircleDot
                      v-if="p.working_now"
                      class="size-3 shrink-0 text-success"
                      aria-hidden="true"
                    />
                    <span class="truncate">{{ p.project_name }}</span>
                    <span class="font-mono tabular-nums text-ink-gray-5"
                      >({{ p.open }})</span
                    >
                    <span v-if="p.working_now" class="sr-only">{{
                      __("working on it now")
                    }}</span>
                  </RouterLink>
                </template>
              </div>

              <div
                class="text-xs text-ink-gray-5 md:text-right md:text-sm"
                :class="person.open ? 'md:text-ink-gray-8' : ''"
              >
                <span class="font-mono tabular-nums">{{ person.open }}</span>
                <span class="md:sr-only"> {{ __("open tasks") }}</span>
              </div>
            </li>
          </ul>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Link, UserAvatar } from "@/components";
import StatTile from "@/components/StatTile.vue";
import TaskStatusBadge from "@/pages/tasky/components/TaskStatusBadge.vue";
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
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCoffee from "~icons/lucide/coffee";
import LucideEye from "~icons/lucide/eye";
import LucideFlag from "~icons/lucide/flag";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucidePause from "~icons/lucide/pause";
import LucideUserStar from "~icons/lucide/user-star";
import LucideUsers from "~icons/lucide/users";

interface Member {
  user: string;
  full_name: string;
  role: string | null;
  is_lead: boolean;
  open: number;
  working: number;
  working_now: boolean;
  working_on: { name: string; subject: string } | null;
}

interface ProjectCard {
  name: string;
  project_name: string;
  customer: string | null;
  project_type: string | null;
  status: string;
  lead: string | null;
  lead_name: string | null;
  expected_start_date: string | null;
  expected_end_date: string | null;
  progress: number;
  counts: {
    total: number;
    done: number;
    open: number;
    working: number;
    review: number;
    on_hold: number;
    overdue: number;
  };
  next_milestone: {
    name: string;
    subject: string;
    due: string | null;
    is_overdue: boolean;
  } | null;
  members: Member[];
}

interface PersonRow {
  user: string;
  full_name: string;
  open: number;
  working: number;
  is_free: boolean;
  projects: {
    project: string;
    project_name: string;
    open: number;
    working_now: boolean;
  }[];
}

interface Portfolio {
  projects: ProjectCard[];
  people: PersonRow[];
  totals: {
    projects: number;
    people_active: number;
    people_free: number | null;
    overdue: number;
  };
}

type StatusFilter = "Open" | "All";

const STATUS_OPTIONS: { key: StatusFilter; label: string }[] = [
  { key: "Open", label: __("Open") },
  { key: "All", label: __("All") },
];

const PEOPLE_GRID =
  "md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_minmax(0,6rem)]";

const route = useRoute();
const router = useRouter();

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const filters = reactive<{ status: StatusFilter; customer: string }>({
  status: queryValue("status") === "all" ? "All" : "Open",
  customer: queryValue("customer"),
});

const portfolio = createResource({
  url: "helpdesk.api.work.get_project_portfolio",
  makeParams: () => ({
    status: filters.status,
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
        status: f.status === "All" ? "all" : undefined,
        customer: f.customer || undefined,
      },
    });
    portfolio.reload();
  }
);

const data = computed(() => portfolio.data as Portfolio | undefined);
const isLoading = computed(() => portfolio.loading && !data.value);
const projects = computed(() => data.value?.projects ?? []);
const people = computed(() => data.value?.people ?? []);

const tiles = computed<
  {
    key: string;
    label: string;
    icon: Component;
    value: number;
    danger?: boolean;
  }[]
>(() => {
  const t = data.value?.totals;
  const all = [
    {
      key: "projects",
      label: __("Projects"),
      icon: LucideFolderKanban,
      value: t?.projects ?? 0,
    },
    {
      key: "people_active",
      label: __("People active"),
      icon: LucideUsers,
      value: t?.people_active ?? 0,
    },
    {
      key: "people_free",
      label: __("Free people"),
      icon: LucideCoffee,
      value: t?.people_free ?? 0,
    },
    {
      key: "overdue",
      label: __("Overdue tasks"),
      icon: LucideAlarmClock,
      value: t?.overdue ?? 0,
      danger: true,
    },
  ];
  // only admins see every agent, so the server leaves "free" out for others
  return t && t.people_free === null
    ? all.filter((tile) => tile.key !== "people_free")
    : all;
});

// people working now sort first, so the preview shows who is busy
const MEMBER_PREVIEW = 6;
const expanded = reactive(new Set<string>());

function visibleMembers(project: ProjectCard) {
  return expanded.has(project.name)
    ? project.members
    : project.members.slice(0, MEMBER_PREVIEW);
}

function toggleMembers(project: string) {
  if (expanded.has(project)) expanded.delete(project);
  else expanded.add(project);
}

function roleLabel(member: Member) {
  if (member.is_lead) return __("Lead");
  return member.role ? __(member.role) : "";
}

function boardRoute(project: string): RouteLocationRaw {
  return { name: "TaskyKanban", params: { projectId: project } };
}

function personRoute(user: string): RouteLocationRaw {
  return { name: "MyWork", query: { user } };
}

function formatDate(date: string) {
  return dayjs(date).format("D MMM YYYY");
}

defineExpose({
  reload: () => portfolio.reload(),
  loading: computed(() => portfolio.loading),
});
</script>
