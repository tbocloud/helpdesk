<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Team targets')"
      :subtitle="__('Everyone\'s targets for the month, side by side.')"
    >
      <template #right-header>
        <TabButtons
          :model-value="view"
          :aria-label="__('View')"
          :options="VIEWS"
          @update:model-value="pickView"
        />
        <Button
          size="md"
          :aria-label="__('Refresh')"
          :loading="teamProgress.loading"
          @click="refresh"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" />
          </template>
        </Button>
        <MonthStepper
          :model-value="month"
          :options="MONTHS"
          @update:model-value="pickMonth"
        />
        <Button
          size="md"
          variant="solid"
          :label="__('Assign targets')"
          @click="router.push({ name: 'SalesTargets', query: { month } })"
        >
          <template #prefix>
            <LucideTarget class="size-4" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="team.error && !team.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('Team targets aren\'t open to you')
              : __('Couldn\'t load the team')
          "
          :message="
            errorText(team.error, __('Check your connection and try again.'))
          "
        >
          <Button
            v-if="!isRefusal"
            :label="__('Try again')"
            @click="team.reload()"
          />
        </TaskyState>

        <template v-else-if="!team.data">
          <div :class="SPLIT" aria-hidden="true">
            <div class="h-56 animate-pulse rounded-xl bg-surface-gray-3" />
            <div class="h-56 animate-pulse rounded-xl bg-surface-gray-3" />
          </div>
          <div
            class="h-96 animate-pulse rounded-xl bg-surface-gray-3"
            aria-busy="true"
            :aria-label="__('Loading')"
          />
        </template>

        <TaskyState
          v-else-if="!people.length"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideUsers"
          :title="__('No one has a target role yet')"
          :message="
            __(
              'Give people the Presales Executive or Sales User role on their user, then assign their targets.'
            )
          "
        />

        <!-- the whole team: the month at a glance, everyone side by side, totals, who is behind -->
        <template v-else-if="view === 'team'">
          <div :class="SPLIT">
            <TeamPaceHero
              :month="month"
              :pace="pace"
              :average="teamAverage"
              :counts="counts"
              :total="people.length"
              :heading-id="heroHeading"
            />
            <section
              class="flex min-w-0 flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4 md:p-5"
              :aria-labelledby="setHeading"
            >
              <div class="flex items-baseline justify-between gap-3">
                <h2
                  :id="setHeading"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Targets set") }}
                </h2>
                <span class="text-2xl font-bold text-ink-gray-9 tabular-nums"
                  >{{ withTargets.length }} / {{ people.length }}</span
                >
              </div>
              <div
                class="h-2 overflow-hidden rounded-full bg-surface-gray-2"
                role="meter"
                :aria-valuenow="withTargets.length"
                aria-valuemin="0"
                :aria-valuemax="people.length"
                :aria-label="__('People with targets')"
              >
                <div
                  class="h-full rounded-full bg-brand"
                  :style="{
                    width: `${(withTargets.length / people.length) * 100}%`,
                  }"
                />
              </div>
              <template v-if="withoutTargets.length">
                <p class="text-sm text-ink-gray-6">
                  {{
                    withoutTargets.length === 1
                      ? __(
                          "1 person has no targets for {0} yet:",
                          monthTitle(month)
                        )
                      : __(
                          "{0} people have no targets for {1} yet:",
                          String(withoutTargets.length),
                          monthTitle(month)
                        )
                  }}
                </p>
                <div class="flex min-w-0 items-center gap-3">
                  <span class="flex shrink-0 -space-x-1.5" aria-hidden="true">
                    <PersonAvatar
                      v-for="person in withoutTargets.slice(0, 5)"
                      :key="person.user"
                      :name="person.full_name"
                      class="ring-2 ring-surface-base"
                    />
                  </span>
                  <p class="line-clamp-2 min-w-0 text-xs text-ink-gray-7">
                    {{ withoutTargets.map((p) => p.full_name).join(", ") }}
                  </p>
                </div>
              </template>
              <p v-else class="flex items-center gap-2 text-sm text-success">
                <LucideCircleCheck class="size-4 shrink-0" aria-hidden="true" />
                {{ __("Everyone has targets for {0}.", monthTitle(month)) }}
              </p>
              <div
                class="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-outline-gray-1 pt-4"
              >
                <span
                  class="flex items-center gap-1.5 text-sm text-ink-gray-7 tabular-nums"
                >
                  <component
                    :is="kpisToConfirm ? LucideClock : LucideCheck"
                    class="size-4 shrink-0"
                    :class="kpisToConfirm ? 'text-info' : 'text-success'"
                    aria-hidden="true"
                  />
                  {{
                    kpisToConfirm === 1
                      ? __("1 KPI waiting to confirm")
                      : __("{0} KPIs waiting to confirm", String(kpisToConfirm))
                  }}
                </span>
                <Button
                  v-if="withoutTargets.length"
                  size="md"
                  variant="solid"
                  :label="
                    withoutTargets.length === 1
                      ? __('Assign to 1 person')
                      : __(
                          'Assign to {0} people',
                          String(withoutTargets.length)
                        )
                  "
                  @click="
                    router.push({
                      name: 'SalesTargets',
                      query: { month, pick: 'without' },
                    })
                  "
                />
              </div>
            </section>
          </div>

          <TeamTargetsMatrix
            v-model:filter="filter"
            :rows="filtered"
            :columns="columns"
            :month="month"
            :currency="team.data.currency"
            :filter-options="filterOptions"
            :heading-id="matrixHeading"
            @open="openPerson"
          />

          <div :class="SPLIT">
            <TeamTotals
              :rows="rows"
              :columns="columns"
              :currency="team.data.currency"
              :pace="pace"
            />
            <BehindPace
              :rows="rows"
              :currency="team.data.currency"
              @open="openPerson"
            />
          </div>
        </template>

        <!-- person by person: the team on the left, the one picked on the right -->
        <div
          v-else
          class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_30rem] lg:items-start xl:grid-cols-[minmax(0,1fr)_38rem] 2xl:grid-cols-[minmax(0,1fr)_44rem]"
        >
          <section
            class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-labelledby="listHeading"
          >
            <h2 :id="listHeading" class="sr-only">{{ __("Team") }}</h2>
            <div
              class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-4"
            >
              <FormControl
                v-model="search"
                type="search"
                size="md"
                class="min-w-[12rem] flex-1"
                :placeholder="__('Search people')"
                :aria-label="__('Search people')"
              >
                <template #prefix>
                  <LucideSearch
                    class="size-4 text-ink-gray-5"
                    aria-hidden="true"
                  />
                </template>
              </FormControl>
              <ViewTabs
                v-model="filter"
                :aria-label="__('Who to show')"
                :options="filterOptions"
              />
            </div>

            <TaskyState
              v-if="!shown.length"
              class="py-10"
              :icon="
                filter === 'behind' && !search
                  ? LucideCircleCheck
                  : LucideSearch
              "
              :title="emptyTitle"
              :message="__('Show everyone to see the whole team.')"
            >
              <Button :label="__('Show everyone')" @click="clearFilters" />
            </TaskyState>
            <ul v-else class="divide-y divide-outline-gray-1">
              <li v-for="row in shown" :key="row.person.user">
                <button
                  type="button"
                  class="grid min-h-[60px] w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                  :class="
                    selected === row.person.user
                      ? 'bg-brand-soft'
                      : 'hover:bg-surface-gray-1'
                  "
                  :aria-pressed="selected === row.person.user"
                  @click="openPerson(row.person.user)"
                >
                  <span class="flex min-w-0 items-center gap-3">
                    <PersonAvatar :name="row.person.full_name" size="lg" />
                    <span class="flex min-w-0 flex-col">
                      <span
                        class="truncate text-[13px] font-semibold text-ink-gray-9"
                        :title="row.person.full_name"
                        >{{ row.person.full_name }}</span
                      >
                      <span class="truncate text-xs text-ink-gray-6">{{
                        row.person.roles.map(roleLabel).join(" · ")
                      }}</span>
                    </span>
                  </span>

                  <span
                    v-if="row.person.target"
                    class="flex flex-col items-end gap-0.5 text-right"
                  >
                    <span
                      class="text-sm font-medium text-ink-gray-8 tabular-nums"
                    >
                      {{
                        row.person.target.criteria.length === 1
                          ? __("1 target")
                          : __(
                              "{0} targets",
                              String(row.person.target.criteria.length)
                            )
                      }}
                    </span>
                    <OverallProgress
                      v-if="row.overall?.percent != null"
                      :percent="row.overall.percent"
                      :behind="row.overall.behind"
                    />
                    <span
                      v-else-if="!row.progress"
                      class="h-1 w-24 animate-pulse rounded-full bg-surface-gray-3"
                      :aria-label="__('Counting')"
                    />
                    <span
                      v-else
                      class="text-xs text-ink-gray-5"
                      :title="row.progress.reason"
                      >{{ uncountedText(row.progress) }}</span
                    >
                  </span>
                  <span
                    v-else
                    class="flex items-center gap-1.5 text-sm text-ink-gray-6"
                  >
                    <LucideCircleDashed class="size-3.5" aria-hidden="true" />
                    {{ __("Not set") }}
                  </span>
                </button>
              </li>
            </ul>
            <div
              class="border-t border-outline-gray-2 px-4 py-3.5 text-xs text-ink-gray-6 tabular-nums"
            >
              {{
                __(
                  "Showing {0} of {1}",
                  String(shown.length),
                  String(people.length)
                )
              }}
            </div>
          </section>

          <section
            class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)]"
            :aria-labelledby="panelHeading"
          >
            <TeamPersonTargets
              v-if="selectedRow"
              :key="`${month}|${selectedRow.person.user}`"
              :person="selectedRow.person"
              :month="month"
              :currency="team.data.currency"
              :progress="selectedRow.progress"
              :heading-id="panelHeading"
              @changed="selectedRow.person.target = $event"
            />
            <TaskyState
              v-else
              class="px-4 py-12"
              :icon="LucideMousePointerClick"
              :title="__('Pick someone to see their targets')"
              :message="
                __(
                  'Each target with what they have achieved so far, and their KPIs to confirm.'
                )
              "
            >
              <h2 :id="panelHeading" class="sr-only">
                {{ __("Targets") }}
              </h2>
            </TaskyState>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import ViewTabs from "@/components/ViewTabs.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl, TabButtons } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideClock from "~icons/lucide/clock";
import LucideLock from "~icons/lucide/lock";
import LucideMousePointerClick from "~icons/lucide/mouse-pointer-click";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideTarget from "~icons/lucide/target";
import LucideUsers from "~icons/lucide/users";
import BehindPace from "./BehindPace.vue";
import MonthStepper from "./MonthStepper.vue";
import OverallProgress from "./OverallProgress.vue";
import TeamPaceHero from "./TeamPaceHero.vue";
import TeamPersonTargets from "./TeamPersonTargets.vue";
import TeamTargetsMatrix from "./TeamTargetsMatrix.vue";
import TeamTotals from "./TeamTotals.vue";
import {
  isKpi,
  monthOptions,
  monthPace,
  monthTitle,
  monthValue,
  overallOf,
  type Criterion,
  type Progress,
  type TeamFilter,
  type TeamRow,
  type TeamStanding,
  type TeamTargets,
} from "./salesTargets";

const MONTHS = monthOptions();
const VIEWS = [
  { label: __("Whole team"), value: "team" },
  { label: __("Person by person"), value: "person" },
];
// the wide summary on the left, its companion card on the right
const SPLIT =
  "grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:items-stretch";
const ROLE_LABELS: Record<string, string> = {
  "Presales Executive": __("Presales Executive"),
  "Sales User": __("Sales User"),
};
const roleLabel = (role: string) => ROLE_LABELS[role] ?? role;

const route = useRoute();
const router = useRouter();
const heroHeading = useId();
const setHeading = useId();
const matrixHeading = useId();
const listHeading = useId();
const panelHeading = useId();

// the month, the view and the person open are in the URL, so a link or a reload opens the
// same view
const month = computed(() => {
  const asked = String(route.query.month || "");
  return MONTHS.some((m) => m.value === asked) ? asked : monthValue();
});
const view = computed(() =>
  route.query.view === "person" ? "person" : "team"
);
const selected = computed(() => String(route.query.employee || ""));
function pickMonth(value: string) {
  router.replace({ query: { ...route.query, month: value } });
}
function pickView(value: string) {
  router.replace({ query: { ...route.query, view: value } });
}
function openPerson(user: string) {
  router.replace({ query: { ...route.query, view: "person", employee: user } });
}

const team = createResource<TeamTargets>({
  url: "helpdesk.api.sales_targets.get_team",
  makeParams: () => ({ month: month.value }),
  auto: true,
});
watch(month, () => team.reload());

// counted from each person's leads on the ERP site: read after the list, so the list shows
// first; Refresh reads past the minute's cache
const fresh = ref(0);
const teamProgress = createResource<Record<string, Progress>>({
  url: "helpdesk.api.sales_targets.get_team_progress",
  makeParams: () => ({ month: month.value, fresh: fresh.value }),
});
watch(
  () => team.data,
  (data) => {
    if (data?.people.some((p) => p.target)) teamProgress.reload();
  }
);
// the progress follows the team's reload (the watch above), then reads from the cache again
function refresh() {
  fresh.value = 1;
  team.reload();
}
watch(
  () => teamProgress.loading,
  (loading) => {
    if (!loading) fresh.value = 0;
  }
);

const isRefusal = computed(
  () => team.error?.exc_type === "SalesTargetsForbiddenError"
);

const people = computed(() => team.data?.people ?? []);
const withTargets = computed(() => people.value.filter((p) => p.target));
const withoutTargets = computed(() => people.value.filter((p) => !p.target));
const pace = computed(() => monthPace(month.value));

function uncountedText(progress: Progress) {
  if (progress.state === "not_started") return __("Not begun");
  if (progress.state === "unavailable") return __("Couldn't count");
  return __("Nothing counted");
}

// ---------- each person's month, and where they stand ----------

// who needs attention first: behind, then the rest by how far they are, not set last
const ORDER: Record<TeamStanding, number> = {
  behind: 0,
  on_track: 1,
  uncounted: 2,
  unset: 3,
};
const rows = computed<TeamRow[]>(() =>
  people.value
    .map((person) => {
      const progress = teamProgress.data?.[person.user] ?? null;
      const overall =
        person.target && progress?.state === "counted"
          ? overallOf(person.target, progress, team.data!.currency)
          : null;
      const standing: TeamStanding = !person.target
        ? "unset"
        : overall?.percent == null
        ? "uncounted"
        : overall.behind
        ? "behind"
        : "on_track";
      return { person, progress, overall, standing };
    })
    .sort(
      (a, b) =>
        ORDER[a.standing] - ORDER[b.standing] ||
        (a.overall?.percent ?? 0) - (b.overall?.percent ?? 0) ||
        a.person.full_name.localeCompare(b.person.full_name)
    )
);
const selectedRow = computed(
  () => rows.value.find((r) => r.person.user === selected.value) ?? null
);
const counts = computed(() => {
  const by: Record<TeamStanding, number> = {
    behind: 0,
    on_track: 0,
    uncounted: 0,
    unset: 0,
  };
  for (const row of rows.value) by[row.standing]++;
  return by;
});
const teamAverage = computed(() => {
  const percents = rows.value
    .map((r) => r.overall?.percent)
    .filter((p): p is number => p != null);
  return percents.length
    ? Math.round(percents.reduce((a, b) => a + b, 0) / percents.length)
    : null;
});
const kpisToConfirm = computed(() =>
  withTargets.value.reduce(
    (sum, p) =>
      sum +
      p.target!.criteria.filter((c) => isKpi(c) && c.kpi_status === "Done")
        .length,
    0
  )
);

// every target given to someone this month, in the order first met; information only
// (Industry, Location) is nothing to track, so it gets no column
const columns = computed(() => {
  const byName = new Map<string, Criterion>();
  for (const person of withTargets.value)
    for (const c of person.target!.criteria)
      if (!c.info_only && !byName.has(c.criterion.toLowerCase()))
        byName.set(c.criterion.toLowerCase(), c);
  return [...byName.values()];
});

// ---------- who is shown ----------

const filter = ref<TeamFilter>("all");
const filterOptions = computed(() => [
  { label: __("Everyone"), value: "all" as const, count: people.value.length },
  {
    label: __("With targets"),
    value: "with" as const,
    count: withTargets.value.length,
  },
  { label: __("Behind"), value: "behind" as const, count: counts.value.behind },
  { label: __("Not set"), value: "unset" as const, count: counts.value.unset },
]);
const filtered = computed(() =>
  rows.value.filter((r) =>
    filter.value === "all"
      ? true
      : filter.value === "with"
      ? !!r.person.target
      : r.standing === filter.value
  )
);

const search = ref("");
const shown = computed(() => {
  const text = search.value.trim().toLowerCase();
  return filtered.value.filter(
    (r) =>
      !text ||
      r.person.full_name.toLowerCase().includes(text) ||
      r.person.user.toLowerCase().includes(text)
  );
});
function clearFilters() {
  search.value = "";
  filter.value = "all";
}
const emptyTitle = computed(() =>
  search.value
    ? __("No one matches “{0}”", search.value)
    : filter.value === "behind"
    ? __("No one is behind pace")
    : __("No one to show here")
);
</script>
