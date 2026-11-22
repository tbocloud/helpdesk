<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Team targets')"
      :subtitle="
        __('How everyone is doing against the targets set for the month.')
      "
    >
      <template #right-header>
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
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
            aria-hidden="true"
          >
            <div
              v-for="n in 4"
              :key="n"
              class="h-24 animate-pulse rounded-xl bg-surface-gray-3"
            />
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

        <template v-else>
          <!-- the month at a glance -->
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          >
            <StatTile
              compact
              :label="__('With targets')"
              :value="`${withTargets.length} / ${people.length}`"
              :sub="
                withTargets.length === people.length
                  ? __('Everyone has targets')
                  : __(
                      '{0} not set',
                      String(people.length - withTargets.length)
                    )
              "
              :meter="(withTargets.length / people.length) * 100"
              tone="success"
            />
            <StatTile
              compact
              :label="__('Team average')"
              :value="teamAverage == null ? '—' : `${teamAverage}%`"
              :sub="
                teamAverage == null
                  ? progressNote
                  : __('of the month\'s targets reached')
              "
            />
            <StatTile
              compact
              :label="__('Behind')"
              :value="String(counts.behind)"
              :value-tone="counts.behind ? 'warning' : undefined"
              :sub="__('{0} on track', String(counts.on_track))"
            />
            <StatTile
              compact
              :label="__('KPIs to confirm')"
              :value="String(kpisToConfirm)"
              :sub="
                kpisToConfirm
                  ? __('Marked done, waiting on you')
                  : __('Nothing waiting')
              "
            />
          </div>

          <div
            class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_30rem] lg:items-start xl:grid-cols-[minmax(0,1fr)_38rem] 2xl:grid-cols-[minmax(0,1fr)_44rem]"
          >
            <!-- the team, who needs attention first -->
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
                <FormControl
                  v-model="roleFilter"
                  type="select"
                  size="md"
                  class="!w-44"
                  :aria-label="__('Role')"
                  :options="roleOptions"
                />
                <FormControl
                  v-model="targetFilter"
                  type="select"
                  size="md"
                  class="!w-48"
                  :aria-label="__('Target')"
                  :options="targetOptions"
                />
                <TabButtons
                  v-model="standingFilter"
                  :aria-label="__('Where they stand')"
                  :options="standingOptions"
                />
              </div>

              <TaskyState
                v-if="!shown.length"
                class="py-10"
                :icon="
                  standingFilter === 'behind' && !search
                    ? LucideCircleCheck
                    : LucideSearch
                "
                :title="emptyTitle"
                :message="__('Show everyone to see the whole team.')"
              >
                <Button :label="__('Show everyone')" @click="clearFilters" />
              </TaskyState>
              <template v-else>
                <div
                  class="grid h-11 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-outline-gray-1 bg-surface-gray-1 px-4 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
                >
                  <span>{{ __("Person") }}</span>
                  <span class="text-right">{{
                    targetFilter === ALL ? __("Month so far") : targetFilter
                  }}</span>
                </div>
                <ul class="divide-y divide-outline-gray-1">
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
                      @click="select(row.person.user)"
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

                      <!-- one target picked: that target for everyone -->
                      <span
                        v-if="targetFilter !== ALL"
                        class="flex flex-col items-end gap-0.5 text-right"
                      >
                        <template v-if="cellFor(row)">
                          <span
                            class="text-sm font-medium text-ink-gray-8 tabular-nums"
                            >{{ cellFor(row)!.figure }}</span
                          >
                          <span
                            class="text-xs"
                            :class="noteClass(cellFor(row)!.tone)"
                            >{{ cellFor(row)!.note }}</span
                          >
                        </template>
                        <span v-else class="text-xs text-ink-gray-5">{{
                          __("Not given")
                        }}</span>
                      </span>

                      <!-- the month overall -->
                      <span
                        v-else
                        class="flex flex-col items-end gap-0.5 text-right"
                      >
                        <template v-if="row.person.target">
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
                            v-else-if="!progressFor(row.person.user)"
                            class="h-1 w-24 animate-pulse rounded-full bg-surface-gray-3"
                            :aria-label="__('Counting')"
                          />
                          <span
                            v-else
                            class="text-xs text-ink-gray-5"
                            :title="progressFor(row.person.user)?.reason"
                            >{{ uncountedText(row.person.user) }}</span
                          >
                        </template>
                        <span
                          v-else
                          class="flex items-center gap-1.5 text-sm text-ink-gray-6"
                        >
                          <LucideCircleDashed
                            class="size-3.5"
                            aria-hidden="true"
                          />
                          {{ __("Not set") }}
                        </span>
                      </span>
                    </button>
                  </li>
                </ul>
              </template>
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

            <!-- the person picked -->
            <section
              class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)]"
              :aria-labelledby="panelHeading"
            >
              <TeamPersonTargets
                v-if="selectedPerson"
                :key="`${month}|${selectedPerson.user}`"
                :person="selectedPerson"
                :month="month"
                :currency="team.data.currency"
                :progress="progressFor(selectedPerson.user)"
                :heading-id="panelHeading"
                @changed="selectedPerson.target = $event"
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
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { INK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl, TabButtons } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideLock from "~icons/lucide/lock";
import LucideMousePointerClick from "~icons/lucide/mouse-pointer-click";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideTarget from "~icons/lucide/target";
import LucideUsers from "~icons/lucide/users";
import MonthStepper from "./MonthStepper.vue";
import OverallProgress from "./OverallProgress.vue";
import TeamPersonTargets from "./TeamPersonTargets.vue";
import {
  figureText,
  isKpi,
  monthOptions,
  monthTitle,
  monthValue,
  overallOf,
  progressOf,
  targetText,
  type Progress,
  type TargetPerson,
  type TeamTargets,
} from "./salesTargets";

const MONTHS = monthOptions();
const ALL = "all";
const ROLE_LABELS: Record<string, string> = {
  "Presales Executive": __("Presales Executive"),
  "Sales User": __("Sales User"),
};
const roleLabel = (role: string) => ROLE_LABELS[role] ?? role;
// a note with no meaning to carry stays quiet gray
const noteClass = (tone: Tone) =>
  tone === "neutral" ? "text-ink-gray-6" : INK[tone];

const route = useRoute();
const router = useRouter();
const listHeading = useId();
const panelHeading = useId();

// the month and the person open are in the URL, so a link or a reload opens the same view
const month = computed(() => {
  const asked = String(route.query.month || "");
  return MONTHS.some((m) => m.value === asked) ? asked : monthValue();
});
const selected = computed(() => String(route.query.employee || ""));
function pickMonth(value: string) {
  router.replace({ query: { ...route.query, month: value } });
}
function select(user: string) {
  router.replace({ query: { ...route.query, employee: user } });
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
const selectedPerson = computed(
  () => people.value.find((p) => p.user === selected.value) ?? null
);

/** A person's progress once read; null while it is being read. */
function progressFor(user: string): Progress | null {
  return teamProgress.data?.[user] ?? null;
}
function uncountedText(user: string) {
  const progress = progressFor(user);
  if (progress?.state === "not_started") return __("Not begun");
  if (progress?.state === "unavailable") return __("Couldn't count");
  return __("Nothing counted");
}

// ---------- each person's month, and where they stand ----------

type Standing = "behind" | "on_track" | "unset" | "uncounted";
interface Row {
  person: TargetPerson;
  overall: { percent: number | null; behind: number } | null;
  standing: Standing;
}

const rows = computed<Row[]>(() =>
  people.value.map((person) => {
    const progress = progressFor(person.user);
    const overall =
      person.target && progress?.state === "counted"
        ? overallOf(person.target, progress, team.data!.currency)
        : null;
    const standing: Standing = !person.target
      ? "unset"
      : overall?.percent == null
      ? "uncounted"
      : overall.behind
      ? "behind"
      : "on_track";
    return { person, overall, standing };
  })
);
const counts = computed(() => {
  const by = { behind: 0, on_track: 0, unset: 0, uncounted: 0 };
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
const progressNote = computed(() =>
  !withTargets.value.length
    ? __("No targets for {0} yet", monthTitle(month.value))
    : teamProgress.loading
    ? __("Counting…")
    : __("Nothing counted yet")
);
const kpisToConfirm = computed(() =>
  withTargets.value.reduce(
    (sum, p) =>
      sum +
      p.target!.criteria.filter((c) => isKpi(c) && c.kpi_status === "Done")
        .length,
    0
  )
);

// ---------- filters ----------

const search = ref("");
const roleFilter = ref(ALL);
const roleOptions = computed(() => [
  { label: __("All roles"), value: ALL },
  ...Object.keys(ROLE_LABELS).map((role) => ({
    label: `${roleLabel(role)} (${
      people.value.filter((p) => p.roles.includes(role)).length
    })`,
    value: role,
  })),
]);

// every target name given to someone this month, in the order first met
const targetOptions = computed(() => {
  const names = new Map<string, string>();
  for (const person of withTargets.value)
    for (const c of person.target!.criteria)
      if (!names.has(c.criterion.toLowerCase()))
        names.set(c.criterion.toLowerCase(), c.criterion);
  return [
    { label: __("All targets"), value: ALL },
    ...[...names.values()].map((name) => ({ label: name, value: name })),
  ];
});
const targetFilter = ref(ALL);
// a month without the picked target falls back to all of them
watch(targetOptions, (options) => {
  if (!options.some((o) => o.value === targetFilter.value))
    targetFilter.value = ALL;
});

const standingFilter = ref<"all" | Standing>("all");
const standingOptions = computed(() => [
  { label: __("All"), value: "all" },
  { label: __("Behind ({0})", String(counts.value.behind)), value: "behind" },
  {
    label: __("On track ({0})", String(counts.value.on_track)),
    value: "on_track",
  },
  { label: __("Not set ({0})", String(counts.value.unset)), value: "unset" },
]);

// who needs attention first: behind, then the rest by how far they are, not set last
const ORDER: Record<Standing, number> = {
  behind: 0,
  on_track: 1,
  uncounted: 2,
  unset: 3,
};
const shown = computed(() => {
  const text = search.value.trim().toLowerCase();
  return rows.value
    .filter(
      (r) =>
        (roleFilter.value === ALL ||
          r.person.roles.includes(roleFilter.value)) &&
        (standingFilter.value === "all" ||
          r.standing === standingFilter.value) &&
        (targetFilter.value === ALL || criterionOf(r.person)) &&
        (!text ||
          r.person.full_name.toLowerCase().includes(text) ||
          r.person.user.toLowerCase().includes(text))
    )
    .sort(
      (a, b) =>
        ORDER[a.standing] - ORDER[b.standing] ||
        (a.overall?.percent ?? 0) - (b.overall?.percent ?? 0) ||
        a.person.full_name.localeCompare(b.person.full_name)
    );
});
function clearFilters() {
  search.value = "";
  roleFilter.value = ALL;
  targetFilter.value = ALL;
  standingFilter.value = "all";
}
const emptyTitle = computed(() =>
  search.value
    ? __("No one matches “{0}”", search.value)
    : standingFilter.value === "behind"
    ? __("No one shown is behind")
    : __("No one matches these filters")
);

// ---------- one target, side by side ----------

function criterionOf(person: TargetPerson) {
  const name = targetFilter.value.toLowerCase();
  return (
    person.target?.criteria.find((c) => c.criterion.toLowerCase() === name) ??
    null
  );
}

/** The picked target for one person: the figure and a note under it, toned by meaning. */
function cellFor(row: Row): {
  figure: string;
  note: string;
  tone: Tone;
} | null {
  const criterion = criterionOf(row.person);
  if (!criterion) return null;
  const currency = team.data!.currency;
  if (criterion.value_type === "Text") {
    if (!isKpi(criterion))
      return {
        figure: targetText(criterion, currency),
        note: __("Information only"),
        tone: "neutral",
      };
    const status = criterion.kpi_status;
    return {
      figure: __("KPI"),
      note:
        status === "Confirmed"
          ? __("Confirmed")
          : status === "Done"
          ? __("Done, to confirm")
          : __("Not done yet"),
      tone:
        status === "Confirmed"
          ? "success"
          : status === "Done"
          ? "info"
          : "neutral",
    };
  }
  const target = targetText(criterion, currency);
  const progress = progressFor(row.person.user);
  const measured =
    criterion.measure && progress?.state === "counted"
      ? progress.criteria?.[criterion.criterion]
      : null;
  if (!criterion.measure)
    return { figure: target, note: __("Target only"), tone: "neutral" };
  if (!measured)
    return {
      figure: target,
      note: progress ? uncountedText(row.person.user) : __("Counting…"),
      tone: "neutral",
    };
  const result = progressOf(criterion, measured, progress!, currency);
  return {
    figure:
      result.achieved == null
        ? __("— of {0}", target)
        : __(
            "{0} of {1}",
            figureText(criterion, result.achieved, currency),
            target
          ),
    note: result.standingText,
    tone: ["done", "on_pace"].includes(result.standing)
      ? "success"
      : result.standing === "none"
      ? "neutral"
      : "warning",
  };
}
</script>
