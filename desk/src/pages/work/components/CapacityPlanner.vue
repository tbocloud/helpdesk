<template>
  <div>
    <!-- Filters -->
    <div
      class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"
      role="group"
      :aria-label="__('Filter capacity')"
    >
      <div
        class="flex gap-1 self-start"
        role="radiogroup"
        :aria-label="__('Plan ahead')"
      >
        <button
          v-for="option in WEEK_OPTIONS"
          :key="option.value"
          type="button"
          role="radio"
          :aria-checked="filters.weeks === option.value"
          class="rounded-md px-2.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :class="
            filters.weeks === option.value
              ? 'bg-surface-gray-3 text-ink-gray-9'
              : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8'
          "
          @click="filters.weeks = option.value"
        >
          {{ option.label }}
        </button>
      </div>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:w-[30rem]">
        <Link
          v-model="filters.department"
          doctype="HD Department"
          :label="__('Department')"
          :placeholder="__('All departments')"
        />
        <Link
          v-model="filters.project"
          doctype="Project"
          :label="__('Project')"
          :placeholder="__('All projects')"
        />
      </div>
    </div>
    <div v-if="hasFilters" class="mt-2 flex justify-end">
      <Button variant="ghost" :label="__('Clear filters')" @click="clear">
        <template #prefix>
          <LucideX class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <TaskyState
      v-if="capacity.error && !data"
      class="mt-6"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the team\'s capacity')"
      :message="
        errorText(capacity.error, __('Check your connection and try again.'))
      "
      error
    >
      <Button :label="__('Retry')" @click="capacity.reload()" />
    </TaskyState>

    <template v-else>
      <p class="mt-4 text-p-sm text-ink-gray-6">
        <template v-if="data">
          {{
            __(
              "{0} to {1}. Available hours follow the work calendar ({2} h a working day); planned hours are what's left of each open task's estimate, spread up to its due date.",
              formatDate(data.start),
              formatDate(data.end),
              formatHours(data.hours_per_day)
            )
          }}
        </template>
        <span
          v-else
          class="inline-block h-3.5 w-2/3 animate-pulse rounded bg-surface-gray-2"
        />
      </p>

      <!-- Summary: a flag tile narrows the people below to those it counts -->
      <div
        class="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4"
        role="group"
        :aria-label="__('Show people')"
      >
        <StatTile
          :label="__('Team load')"
          :value="totals?.utilisation != null ? `${totals.utilisation}%` : '–'"
          :sub="
            totals
              ? __(
                  '{0} of {1} h planned',
                  formatHours(totals.planned),
                  formatHours(totals.available)
                )
              : ''
          "
          :icon="LucideGauge"
          :loading="isLoading"
        />
        <StatTile
          v-for="tile in flagTiles"
          :key="tile.flag"
          :label="tile.label"
          :value="tile.value"
          :sub="tile.sub"
          :icon="tile.icon"
          :icon-tone="tile.tone"
          :value-tone="tile.value ? tile.tone : 'neutral'"
          :loading="isLoading"
          :pressed="load === tile.flag"
          :aria-controls="listId"
          @click="setLoad(tile.flag)"
        />
      </div>

      <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <!-- People -->
        <SectionCard
          :id="listId"
          class="overflow-hidden xl:col-span-2"
          :title="loadTile ? loadTile.label : __('People')"
          :count="isLoading ? undefined : people.length"
          :aria-busy="capacity.loading"
        >
          <template #actions>
            <FormControl
              v-model="sort"
              type="select"
              class="w-40"
              :options="SORTS"
              :aria-label="__('Sort people')"
            />
          </template>

          <div
            v-if="isLoading"
            :aria-label="__('Loading')"
            class="divide-y divide-outline-gray-1"
          >
            <div
              v-for="i in 5"
              :key="i"
              class="flex items-center gap-3 px-4 py-3.5"
            >
              <div
                class="size-8 shrink-0 animate-pulse rounded-full bg-surface-gray-2"
              />
              <div
                class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2"
              />
              <div
                class="ml-auto h-2 w-1/3 animate-pulse rounded-full bg-surface-gray-2"
              />
            </div>
          </div>

          <TaskyState
            v-else-if="!everyone.length"
            :icon="LucideUsers"
            :title="__('No one to plan for yet')"
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
            :message="loadTile?.empty"
          >
            <Button :label="__('Show everyone')" @click="setLoad('')" />
          </TaskyState>

          <ul v-else role="list" class="divide-y divide-outline-gray-1">
            <li v-for="person in people" :key="person.user">
              <div
                class="flex flex-col gap-3 px-4 py-3 md:grid md:items-center md:gap-4"
                :class="ROW_GRID"
              >
                <div class="flex min-w-0 items-center gap-3">
                  <UserAvatar :name="person.user" size="lg" />
                  <div class="min-w-0 flex-1">
                    <RouterLink
                      :to="{ name: 'MyWork', query: { user: person.user } }"
                      class="block truncate rounded text-base text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      :title="__('Open the work of {0}', person.full_name)"
                    >
                      {{ person.full_name }}
                    </RouterLink>
                    <div class="mt-0.5 flex flex-wrap gap-1">
                      <TaskyBadge v-bind="flagBadge(person.flag)" />
                      <TaskyBadge
                        v-if="person.leave_days"
                        tone="info"
                        :icon="LucideTreePalm"
                        :label="
                          __('{0} day(s) on leave', String(person.leave_days))
                        "
                      />
                    </div>
                  </div>
                </div>

                <!-- a meter per week -->
                <div
                  class="grid gap-3"
                  :class="WEEK_COLUMNS[person.weeks.length] ?? WEEK_COLUMNS[4]"
                >
                  <div
                    v-for="(week, i) in person.weeks"
                    :key="week.start"
                    class="flex min-w-0 flex-col gap-1"
                  >
                    <span class="truncate text-xs text-ink-gray-5">
                      {{ weekLabel(i) }}
                    </span>
                    <span
                      class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                      role="meter"
                      :aria-valuenow="week.utilisation ?? 0"
                      aria-valuemin="0"
                      aria-valuemax="100"
                      :aria-valuetext="loadText(week)"
                      :aria-label="
                        __('{0}, {1}', person.full_name, weekLabel(i))
                      "
                    >
                      <span
                        class="block h-full rounded-full"
                        :class="
                          isOver(week) ? 'bg-danger' : 'bg-surface-gray-7'
                        "
                        :style="{ width: `${meterWidth(week)}%` }"
                      />
                    </span>
                    <span
                      class="flex items-center gap-1 whitespace-nowrap font-mono text-xs tabular-nums"
                      :class="isOver(week) ? 'text-danger' : 'text-ink-gray-6'"
                    >
                      <LucideTriangleAlert
                        v-if="isOver(week)"
                        class="size-3"
                        aria-hidden="true"
                      />
                      {{ hoursOf(week) }}
                    </span>
                  </div>
                </div>

                <div
                  class="flex items-center justify-between gap-3 md:justify-end"
                >
                  <span
                    class="font-mono text-sm tabular-nums text-ink-gray-8"
                    :title="__('Planned of available hours')"
                  >
                    {{ hoursOf(person) }}
                  </span>
                  <!-- 44px tall on phones, a compact icon button from md -->
                  <button
                    type="button"
                    class="flex h-11 items-center gap-1.5 rounded-md px-2 text-sm text-ink-gray-6 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 md:size-7 md:justify-center md:px-0"
                    :aria-expanded="expanded.has(person.user)"
                    :aria-controls="`${listId}-${person.user}`"
                    @click="toggle(person.user)"
                  >
                    <span class="md:sr-only">{{ __("Details") }}</span>
                    <span class="sr-only">{{ person.full_name }}</span>
                    <LucideChevronDown
                      class="size-4 transition-transform motion-reduce:transition-none"
                      :class="expanded.has(person.user) ? 'rotate-180' : ''"
                      aria-hidden="true"
                    />
                  </button>
                </div>
              </div>

              <CapacityDetail
                v-if="expanded.has(person.user)"
                :id="`${listId}-${person.user}`"
                :person="person"
              />
            </li>
          </ul>
        </SectionCard>

        <!-- Who has room -->
        <SectionCard
          :title="roomTitle"
          :description="roomDescription"
          :aria-busy="capacity.loading"
        >
          <div class="flex flex-col gap-3 p-4">
            <FormControl
              v-model.number="extraHours"
              type="number"
              min="0"
              :label="__('New work, in hours')"
              :placeholder="__('e.g. 16')"
              :description="
                __(
                  'See who could take it on within the window, after their planned work.'
                )
              "
            />
          </div>
          <div v-if="isLoading" class="flex flex-col gap-3 px-4 pb-4">
            <div
              v-for="i in 3"
              :key="i"
              class="h-8 animate-pulse rounded bg-surface-gray-2"
            />
          </div>
          <p
            v-else-if="!room.length"
            class="px-4 pb-4 text-p-sm text-ink-gray-6"
            role="status"
          >
            {{ roomEmpty }}
          </p>
          <ul
            v-else
            role="list"
            class="divide-y divide-outline-gray-1 border-t border-outline-gray-1"
          >
            <li
              v-for="entry in room.slice(0, ROOM_LIMIT)"
              :key="entry.person.user"
            >
              <RouterLink
                :to="{ name: 'MyWork', query: { user: entry.person.user } }"
                class="flex min-h-11 items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
              >
                <UserAvatar :name="entry.person.user" size="md" />
                <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">
                  {{ entry.person.full_name }}
                </span>
                <span class="text-right">
                  <span
                    class="block font-mono text-sm tabular-nums text-ink-gray-9"
                  >
                    {{ __("{0} h free", formatHours(entry.free)) }}
                  </span>
                  <span
                    v-if="entry.after != null"
                    class="block font-mono text-xs tabular-nums text-ink-gray-5"
                  >
                    {{ entry.before }}% → {{ entry.after }}%
                  </span>
                </span>
              </RouterLink>
            </li>
          </ul>
          <p
            v-if="room.length > ROOM_LIMIT"
            class="border-t border-outline-gray-1 px-4 py-2 text-sm text-ink-gray-5"
          >
            {{ __("{0} more", String(room.length - ROOM_LIMIT)) }}
          </p>
        </SectionCard>
      </div>

      <!-- Where the hours go -->
      <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SectionCard
          v-for="group in groups"
          :key="group.key"
          :title="group.title"
          :description="__('Planned hours in the window')"
        >
          <div v-if="isLoading" class="flex flex-col gap-3 p-4">
            <div
              v-for="i in 3"
              :key="i"
              class="h-6 animate-pulse rounded bg-surface-gray-2"
            />
          </div>
          <p
            v-else-if="!group.rows.length"
            class="p-4 text-p-sm text-ink-gray-6"
          >
            {{ __("No planned work in these weeks.") }}
          </p>
          <ul v-else role="list" class="flex flex-col gap-3 p-4">
            <li
              v-for="row in group.rows.slice(0, GROUP_LIMIT)"
              :key="row.key"
              class="flex flex-col gap-1"
            >
              <div class="flex items-baseline justify-between gap-3 text-sm">
                <span
                  class="min-w-0 truncate"
                  :class="row.muted ? 'text-ink-gray-5' : 'text-ink-gray-8'"
                >
                  {{ row.label }}
                </span>
                <span class="shrink-0 font-mono tabular-nums text-ink-gray-7">
                  {{ formatHours(row.hours) }} h
                  <span v-if="row.people" class="text-ink-gray-5">
                    · {{ peopleCount(row.people) }}
                  </span>
                </span>
              </div>
              <span
                class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                aria-hidden="true"
              >
                <span
                  class="block h-full rounded-full bg-surface-gray-7"
                  :style="{ width: `${share(row.hours)}%` }"
                />
              </span>
            </li>
          </ul>
          <p
            v-if="group.rows.length > GROUP_LIMIT"
            class="border-t border-outline-gray-1 px-4 py-2 text-sm text-ink-gray-5"
          >
            {{ __("{0} more", String(group.rows.length - GROUP_LIMIT)) }}
          </p>
        </SectionCard>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Link, UserAvatar } from "@/components";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideGauge from "~icons/lucide/gauge";
import LucideTreePalm from "~icons/lucide/tree-palm";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
import CapacityDetail from "./CapacityDetail.vue";
import {
  FLAGS,
  flagBadge,
  formatHours,
  hoursOf,
  isOver,
  loadText,
  meterWidth,
  type Capacity,
  type Flag,
  type PersonCapacity,
} from "./capacity";

const WEEK_OPTIONS = [
  { value: 1, label: __("1 week") },
  { value: 2, label: __("2 weeks") },
  { value: 4, label: __("4 weeks") },
];
const DEFAULT_WEEKS = 2;

type Sort = "load" | "free" | "name";
const SORTS: { label: string; value: Sort }[] = [
  { label: __("Most loaded first"), value: "load" },
  { label: __("Most free hours"), value: "free" },
  { label: __("Name"), value: "name" },
];
const SORT_COMPARE: Record<
  Exclude<Sort, "load">,
  (a: PersonCapacity, b: PersonCapacity) => number
> = {
  free: (a, b) => b.free - a.free || a.full_name.localeCompare(b.full_name),
  name: (a, b) => a.full_name.localeCompare(b.full_name),
};

const ROW_GRID = "md:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_minmax(0,9rem)]";
// full class strings so Tailwind finds them; four weeks wrap to two rows below lg
const WEEK_COLUMNS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  4: "grid-cols-2 lg:grid-cols-4",
};
const ROOM_LIMIT = 6;
const GROUP_LIMIT = 8;

const route = useRoute();
const router = useRouter();
const listId = `capacity-people-${useId()}`;

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

function weeksFromUrl() {
  const value = Number(queryValue("weeks"));
  return WEEK_OPTIONS.some((o) => o.value === value) ? value : DEFAULT_WEEKS;
}

const filters = reactive({
  weeks: weeksFromUrl(),
  department: queryValue("department"),
  project: queryValue("project"),
});

const hasFilters = computed(() => !!(filters.department || filters.project));

function clear() {
  filters.department = "";
  filters.project = "";
}

const capacity = createResource({
  url: "helpdesk.api.capacity.get_capacity",
  makeParams: () => ({
    weeks: filters.weeks,
    department: filters.department || null,
    project: filters.project || null,
  }),
  auto: true,
});

// keep the filters in the URL so the plan can be shared
watch(
  () => ({ ...filters }),
  (f) => {
    router.replace({
      query: {
        ...route.query,
        weeks: f.weeks === DEFAULT_WEEKS ? undefined : String(f.weeks),
        department: f.department || undefined,
        project: f.project || undefined,
      },
    });
    capacity.reload();
  }
);

const load = computed<Flag | "">(() => {
  const value = queryValue("load") as Flag;
  return FLAGS.includes(value) ? value : "";
});

function setLoad(next: Flag | "") {
  const value = load.value === next ? "" : next;
  router.replace({ query: { ...route.query, load: value || undefined } });
}

const sort = computed<Sort>({
  get: () => {
    const value = queryValue("sort") as Sort;
    return SORTS.some((s) => s.value === value) ? value : "load";
  },
  set: (value) =>
    router.replace({
      query: { ...route.query, sort: value === "load" ? undefined : value },
    }),
});

const data = computed(() => capacity.data as Capacity | undefined);
const isLoading = computed(() => capacity.loading && !data.value);
const totals = computed(() => data.value?.totals);
const everyone = computed(() => data.value?.people ?? []);

const people = computed(() => {
  const shown = load.value
    ? everyone.value.filter((p) => p.flag === load.value)
    : [...everyone.value];
  return sort.value === "load" ? shown : shown.sort(SORT_COMPARE[sort.value]);
});

const flagTiles = computed(() => {
  const counts = totals.value?.flags;
  return [
    {
      flag: "overloaded" as const,
      sub: __("Over 100% of their hours"),
      empty: __("No one has more planned than they have time for."),
    },
    {
      flag: "busy" as const,
      sub: __("80 to 100% planned"),
      empty: __("No one is close to full."),
    },
    {
      flag: "available" as const,
      sub: __("Under 80% planned"),
      empty: __("Everyone is busy or overloaded."),
    },
  ].map((tile) => ({
    ...tile,
    ...flagBadge(tile.flag),
    value: counts?.[tile.flag] ?? 0,
  }));
});

const loadTile = computed(() =>
  flagTiles.value.find((t) => t.flag === load.value)
);

const expanded = reactive(new Set<string>());

function toggle(user: string) {
  if (expanded.has(user)) expanded.delete(user);
  else expanded.add(user);
}

function weekLabel(index: number) {
  const week = data.value?.weeks[index];
  if (!week) return "";
  const start = dayjs(week.start);
  const end = dayjs(week.end);
  return start.month() === end.month()
    ? `${start.format("D")}–${end.format("D MMM")}`
    : `${start.format("D MMM")} – ${end.format("D MMM")}`;
}

// "Who's free next week": the week after this one, or this week when it's all we plan
// from the server's today, not the browser's clock
const roomWeekIndex = computed(() => {
  const weeks = data.value?.weeks ?? [];
  const today = dayjs(data.value?.today);
  const thisSunday = today.add((7 - today.day()) % 7, "day");
  const next = weeks.findIndex((w) =>
    dayjs(w.start).isAfter(thisSunday, "day")
  );
  return next === -1 ? 0 : next;
});

const isNextWeek = computed(() => {
  const week = data.value?.weeks[roomWeekIndex.value];
  return !!week && dayjs(week.start).isAfter(dayjs(data.value?.today), "day");
});

const extraHours = ref<number | "">("");
const wanted = computed(() =>
  typeof extraHours.value === "number" && extraHours.value > 0
    ? extraHours.value
    : 0
);

const roomTitle = computed(() =>
  wanted.value
    ? __("Who could take it on")
    : isNextWeek.value
    ? __("Who's free next week")
    : __("Who's free this week")
);

const roomDescription = computed(() =>
  wanted.value
    ? __(
        "Free hours from {0} to {1}",
        formatDate(data.value?.start),
        formatDate(data.value?.end)
      )
    : __("Free hours in {0}", weekLabel(roomWeekIndex.value))
);

interface Room {
  person: PersonCapacity;
  free: number;
  before?: number | null;
  after?: number | null;
}

const room = computed<Room[]>(() => {
  if (wanted.value) {
    return everyone.value
      .filter((p) => p.free >= wanted.value)
      .map((p) => ({
        person: p,
        free: p.free,
        before: p.utilisation,
        after: p.available
          ? Math.round(((p.planned + wanted.value) / p.available) * 100)
          : null,
      }))
      .sort((a, b) => b.free - a.free);
  }
  return everyone.value
    .map((p) => {
      const week = p.weeks[roomWeekIndex.value];
      return {
        person: p,
        free: week ? Math.max(week.available - week.planned, 0) : 0,
        flag: week?.flag,
      };
    })
    .filter((entry) => entry.flag === "available")
    .map(({ person, free }) => ({ person, free: Math.round(free * 10) / 10 }))
    .sort((a, b) => b.free - a.free);
});

const roomEmpty = computed(() => {
  if (!everyone.value.length) return __("No one to plan for yet.");
  if (wanted.value)
    return filters.weeks < 4
      ? __(
          "No one has {0} free hours in these weeks. Try 4 weeks, or split the work.",
          formatHours(wanted.value)
        )
      : __(
          "No one has {0} free hours in these weeks. Split the work or move a due date.",
          formatHours(wanted.value)
        );
  return __("Everyone is at least 80% planned that week.");
});

const groups = computed(() => [
  {
    key: "department",
    title: __("By department"),
    rows: (data.value?.by_department ?? []).map((row) => ({
      key: row.other ? "__other__" : row.department ?? "",
      label: row.other
        ? __("Other projects")
        : row.department ?? __("No department"),
      muted: !row.department,
      hours: row.hours,
      people: 0,
    })),
  },
  {
    key: "project",
    title: __("By project"),
    rows: (data.value?.by_project ?? []).map((row) => ({
      key: row.project ?? "",
      label: row.project_name ?? __("Other projects"),
      muted: !row.project,
      hours: row.hours,
      people: row.people,
    })),
  },
]);

function share(hours: number) {
  const planned = totals.value?.planned ?? 0;
  return planned ? Math.min((hours / planned) * 100, 100) : 0;
}

function peopleCount(n: number) {
  return n === 1 ? __("1 person") : __("{0} people", String(n));
}

function formatDate(date?: string) {
  return date ? dayjs(date).format("D MMM") : "";
}

defineExpose({
  reload: () => capacity.reload(),
  loading: computed(() => capacity.loading),
});
</script>
