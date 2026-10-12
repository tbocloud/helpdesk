<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Scoreboard") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="dashboard.loading"
          :aria-label="__('Refresh')"
          @click="dashboard.reload()"
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
              "Who finished what, on time, and who is champion. Each task counts by its weight and how well it was done, by its due date; hours count only a little."
            )
          }}
          <button
            v-if="data"
            type="button"
            class="rounded text-ink-gray-8 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            @click="showRules = true"
          >
            {{ __("How weight works") }}
          </button>
        </p>
        <ScoreRulesDialog
          v-if="data"
          v-model:open="showRules"
          :rules="data.rules"
        />

        <!-- period and department: everything below follows them -->
        <div
          class="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
        >
          <TabButtons
            v-model="period"
            class="hidden self-start sm:block"
            size="md"
            :aria-label="__('Period')"
            :options="PERIODS.map((p) => ({ label: p.label, value: p.key }))"
          />
          <FormControl
            v-model="period"
            class="sm:hidden"
            type="select"
            :label="__('Period')"
            :options="PERIODS.map((p) => ({ label: p.label, value: p.key }))"
          />
          <FormControl
            v-if="departmentOptions.length > 1"
            v-model="department"
            class="md:w-56"
            type="select"
            :aria-label="__('Department')"
            :options="departmentOptions"
          />
        </div>
        <!-- which period: step back and forth, or pick a month; every month starts fresh on the 1st -->
        <div
          v-if="data"
          class="mt-3 flex flex-wrap items-center gap-x-2 gap-y-2"
          role="group"
          :aria-label="__('Choose the period')"
        >
          <div class="flex min-w-0 items-center gap-1">
            <Button
              variant="ghost"
              :aria-label="__('Previous')"
              :tooltip="__('Previous')"
              @click="step(-1)"
            >
              <template #icon>
                <LucideChevronLeft class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <h2
              class="min-w-0 truncate px-1 text-base-medium tabular-nums text-ink-gray-9"
              aria-live="polite"
            >
              {{ periodName }}
            </h2>
            <Button
              variant="ghost"
              :aria-label="__('Next')"
              :tooltip="__('Next')"
              :disabled="data.period.current"
              @click="step(1)"
            >
              <template #icon>
                <LucideChevronRight class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <Button
            v-if="!data.period.current"
            variant="subtle"
            :label="__('Back to {0}', periodMeta.current)"
            @click="day = ''"
          />
          <FormControl
            v-if="MONTH_PERIODS.includes(period)"
            v-model="pickedMonth"
            class="w-full sm:ms-auto sm:w-48"
            type="select"
            :aria-label="__('Month')"
            :options="monthOptions(data.period.earliest, today)"
          />
        </div>
        <p v-if="data" class="mt-2 text-p-sm tabular-nums text-ink-gray-5">
          {{ rangeText(data.period.start, data.period.end) }} ·
          {{
            __(
              "compared with {0}, the same point {1}",
              rangeText(data.period.compare_start, data.period.compare_end),
              periodMeta.previous
            )
          }}
        </p>

        <TaskyState
          v-if="dashboard.error && !data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the scoreboard')"
          :message="
            errorText(
              dashboard.error,
              __('Check your connection and try again.')
            )
          "
          error
        >
          <Button :label="__('Retry')" @click="dashboard.reload()" />
          <Button
            v-if="department"
            variant="ghost"
            :label="__('Show the whole team')"
            @click="department = ''"
          />
        </TaskyState>

        <div
          v-else
          class="transition-opacity"
          :class="dashboard.loading && data ? 'opacity-60' : ''"
          :aria-busy="dashboard.loading"
        >
          <!-- champion and the headline numbers -->
          <div
            class="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
          >
            <div class="flex min-w-0 flex-col gap-3">
              <ChampionCard
                :title="championTitle"
                :period="periodName"
                :champion="data?.champion ?? null"
                :closed="data?.period.closed"
                :loading="!data"
              />
              <!-- the period before's champion, as kept when it closed -->
              <NativeButton
                v-if="data?.previous_champion"
                type="button"
                class="flex min-w-0 items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3 text-left transition-colors hover:border-outline-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :aria-label="
                  __(
                    'Show {0}: champion {1}, score {2}',
                    previousName,
                    data.previous_champion.name,
                    String(data.previous_champion.score)
                  )
                "
                @click="showPrevious"
              >
                <LucideTrophy
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="truncate text-sm text-ink-gray-8">
                    <span class="text-ink-gray-6">{{ previousName }}:</span>
                    {{ data.previous_champion.name }}
                    <span class="font-mono tabular-nums text-ink-gray-6">
                      · {{ data.previous_champion.score }}
                    </span>
                  </span>
                  <span
                    v-if="data.previous_champion.reasons.length"
                    class="truncate text-xs text-ink-gray-5"
                    >{{ data.previous_champion.reasons[0] }}</span
                  >
                </span>
                <LucideChevronRight
                  class="size-4 shrink-0 text-ink-gray-4"
                  aria-hidden="true"
                />
              </NativeButton>
            </div>
            <div
              class="grid grid-cols-2 gap-3"
              :class="showPosts ? 'xl:grid-cols-3' : ''"
            >
              <StatTile
                :label="__('Tasks finished')"
                :value="data?.summary.tasks ?? 0"
                :icon="LucideCircleCheck"
                icon-tone="success"
                :loading="!data"
                :sub="__('{0} weighted work', weightText(data?.summary.weight))"
                v-bind="change('tasks')"
              />
              <StatTile
                :label="__('On time')"
                :value="pctText(data?.summary.on_time_pct)"
                :icon="LucideCalendarCheck"
                :icon-tone="onTimeTone(data?.summary.on_time_pct)"
                :loading="!data"
                v-bind="change('on_time_pct', ' pts')"
              />
              <StatTile
                v-if="!data?.period.closed"
                :label="__('Overdue now')"
                :value="data?.summary.overdue ?? 0"
                :icon="LucideAlarmClock"
                icon-tone="danger"
                :value-tone="data?.summary.overdue ? 'danger' : 'neutral'"
                :loading="!data"
                :sub="__('Open tasks past their due date')"
              />
              <StatTile
                v-if="showPosts"
                :label="__('Posts published')"
                :value="data?.summary.posts ?? 0"
                :icon="LucideCalendarDays"
                icon-tone="success"
                :loading="!data"
                v-bind="postsChange"
              />
              <StatTile
                :label="__('Hours logged')"
                :value="hoursText(data?.summary.hours ?? 0)"
                :icon="LucideClock"
                icon-tone="info"
                :loading="!data"
                v-bind="change('hours', 'h')"
              />
            </div>
          </div>

          <div
            class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]"
          >
            <!-- the list: departments, people or projects -->
            <div class="flex min-w-0 flex-col gap-4">
              <div
                class="-mx-1 max-w-full self-start overflow-x-auto px-1 pb-1"
              >
                <TabButtons
                  v-model="view"
                  size="md"
                  :aria-label="__('Show')"
                  :options="
                    VIEWS.map((v) => ({ label: v.label, value: v.key }))
                  "
                />
              </div>

              <TeamYearMonths
                v-if="data?.months"
                :months="data.months"
                @open="openMonth"
              />
              <div
                v-if="!data"
                class="h-64 animate-pulse rounded-lg bg-surface-gray-2"
              />
              <TeamDepartmentList
                v-else-if="view === 'departments'"
                :departments="data.departments"
                :groups="data.access.groups"
                @open="openDepartment"
                @open-group="openGroup"
              />
              <TeamPeopleList
                v-else-if="view === 'people'"
                :people="data.people"
                :open="person"
                @toggle="person = $event"
              />
              <TeamProjectList
                v-else-if="view === 'projects'"
                :projects="data.projects"
                :highlight="project"
              />
              <TeamRepeatIssues
                v-else
                :period="period"
                :department="scope.department"
                :group="scope.group"
                :day="day"
              />
            </div>

            <!-- trend, analysis and this year's champions -->
            <aside class="flex min-w-0 flex-col gap-4">
              <TeamAnalysis
                v-if="data"
                :analysis="data.analysis"
                :period="period"
                :department="data.department"
                :group="data.group"
                :can-refresh="data.access.can_refresh"
              />
              <SectionCard v-if="data?.trend" :title="__('Tasks finished')">
                <div class="px-3 py-3">
                  <TeamTrendChart :trend="data.trend" />
                </div>
              </SectionCard>
              <SectionCard
                v-if="data"
                :title="__('Champions this year')"
                :description="historyNote"
              >
                <p
                  v-if="!data.history.length"
                  class="px-4 py-3 text-p-sm text-ink-gray-6"
                >
                  {{
                    __(
                      "None yet. A champion is kept when each week, month, quarter, half and year ends."
                    )
                  }}
                </p>
                <ul v-else role="list">
                  <li
                    v-for="row in data.history"
                    :key="`${row.period_type}-${row.start}`"
                    class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
                  >
                    <Avatar
                      :label="row.name"
                      :image="row.image || undefined"
                      size="md"
                    />
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-sm text-ink-gray-9">
                        {{ row.name }}
                      </div>
                      <div class="text-xs text-ink-gray-5">
                        {{ historyLabel(row) }}
                      </div>
                    </div>
                    <span
                      class="font-mono text-sm tabular-nums text-ink-gray-7"
                      :aria-label="__('Score {0}', String(row.score))"
                    >
                      {{ row.score }}
                    </span>
                  </li>
                </ul>
              </SectionCard>
            </aside>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { onTimeTone, pctText } from "@/pages/performance/performanceMeta";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Avatar,
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarCheck from "~icons/lucide/calendar-check";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import ChampionCard from "./components/ChampionCard.vue";
import ScoreRulesDialog from "./components/ScoreRulesDialog.vue";
import TeamAnalysis from "./components/TeamAnalysis.vue";
import TeamDepartmentList from "./components/TeamDepartmentList.vue";
import TeamPeopleList from "./components/TeamPeopleList.vue";
import TeamProjectList from "./components/TeamProjectList.vue";
import TeamRepeatIssues from "./components/TeamRepeatIssues.vue";
import TeamTrendChart from "./components/TeamTrendChart.vue";
import TeamYearMonths from "./components/TeamYearMonths.vue";
import NativeButton from "@/components/NativeButton";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideTrophy from "~icons/lucide/trophy";
import {
  delta,
  GROUP_PREFIX,
  historyLabel,
  hoursText,
  monthOptions,
  periodTitle,
  PERIODS,
  rangeText,
  VIEWS,
  weightText,
  type Dashboard,
  type PeriodKey,
  type ViewKey,
} from "./teamDashboardMeta";

const route = useRoute();
const router = useRouter();
const query = (key: string) =>
  typeof route.query[key] === "string" ? (route.query[key] as string) : "";

const period = ref<PeriodKey>(
  PERIODS.some((p) => p.key === query("period"))
    ? (query("period") as PeriodKey)
    : "week"
);
// one filter for both: a department's name, or GROUP_PREFIX and a group's name
const department = ref(
  query("group") ? GROUP_PREFIX + query("group") : query("department")
);
const scope = computed(() =>
  department.value.startsWith(GROUP_PREFIX)
    ? { department: "", group: department.value.slice(GROUP_PREFIX.length) }
    : { department: department.value, group: "" }
);
const showRules = ref(false);
// a past day whose period the page shows; empty for the period in progress
const day = ref(/^\d{4}-\d{2}-\d{2}$/.test(query("day")) ? query("day") : "");
const today = dayjs().format("YYYY-MM-DD");
// the periods the month picker applies to: they live inside a month
const MONTH_PERIODS: string[] = ["today", "week", "month"];
const view = ref<ViewKey>(
  VIEWS.some((v) => v.key === query("view"))
    ? (query("view") as ViewKey)
    : "departments"
);
const person = ref(query("person"));
const project = ref(query("project"));

const dashboard = createResource({
  url: "helpdesk.api.team_dashboard.get_team_dashboard",
  makeParams: () => ({
    period: period.value,
    department: scope.value.department || null,
    group: scope.value.group || null,
    day: day.value || null,
  }),
  auto: true,
});
const data = computed(() => dashboard.data as Dashboard | undefined);
const periodMeta = computed(
  () => PERIODS.find((p) => p.key === period.value) || PERIODS[1]
);

const departmentOptions = computed(() => {
  const access = data.value?.access;
  if (!access) return [];
  return [
    { label: __("Whole team"), value: "" },
    ...access.groups.map((g) => ({
      label: __("{0} group", g.group),
      value: GROUP_PREFIX + g.group,
    })),
    ...access.departments.map((d) => ({ label: d, value: d })),
  ];
});

// "ERP group", "GrowthX" or nothing for the whole team
const scopeName = computed(() => {
  const d = data.value;
  if (d?.group) return __("{0} group", d.group);
  return d?.department || "";
});
const championTitle = computed(() =>
  scopeName.value ? __("{0} champion", scopeName.value) : __("Champion")
);
const historyNote = computed(() =>
  scopeName.value
    ? __("{0}, kept when each period ends.", scopeName.value)
    : __("The whole team, kept when each period ends.")
);

type Compared = "tasks" | "on_time_pct" | "hours" | "posts";
/** StatTile's change line; more done, more on time and more hours read as better. */
function change(key: Compared, unit = "") {
  const s = data.value?.summary;
  if (!s) return {};
  const d = delta(s[key], s.previous[key]);
  const previous = periodMeta.value.previous;
  let deltaText: string;
  if (d == null) deltaText = __("Nothing to compare with yet");
  else if (!d) deltaText = __("Same as {0}", previous);
  else deltaText = __("{0}{1} vs {2}", String(Math.abs(d)), unit, previous);
  return {
    delta: d,
    deltaText,
    deltaTone: (d ?? 0) > 0 ? ("success" as const) : ("neutral" as const),
  };
}
const showPosts = computed(() => {
  const s = data.value?.summary;
  return !!s && !!(s.posts || s.posts_missed || s.previous.posts);
});
const postsChange = computed(() => {
  const s = data.value?.summary;
  if (!s?.posts_missed) return change("posts");
  return { sub: __("{0} missed their date", String(s.posts_missed)) };
});

const periodName = computed(() => {
  const p = data.value?.period;
  if (!p) return periodMeta.value.label;
  return periodTitle(p.key, p.start, p.end, p.current);
});

/** A day of the period before or after; the period in progress needs no day. */
function step(direction: -1 | 1) {
  const p = data.value?.period;
  if (!p) return;
  const target =
    direction < 0
      ? dayjs(p.start).subtract(1, "day")
      : dayjs(p.end).add(1, "day");
  day.value = target.isBefore(dayjs(today), "day")
    ? target.format("YYYY-MM-DD")
    : "";
}

/** The month the page is in; picking one shows its last day's period (today in this month). */
const pickedMonth = computed({
  get: () => dayjs(data.value?.period.start).format("YYYY-MM"),
  set: (month: string) => {
    const last = dayjs(`${month}-01`).endOf("month");
    day.value = last.isBefore(dayjs(today), "day")
      ? last.format("YYYY-MM-DD")
      : "";
  },
});

const previousName = computed(() => {
  const c = data.value?.previous_champion;
  const p = data.value?.period;
  if (!c?.start || !c.end || !p) return "";
  return periodTitle(p.key, c.start, c.end);
});

function showPrevious() {
  const c = data.value?.previous_champion;
  if (c?.end) day.value = c.end;
}

function openMonth(month: string) {
  const last = dayjs(month).endOf("month");
  period.value = "month";
  day.value = last.isBefore(dayjs(today), "day")
    ? last.format("YYYY-MM-DD")
    : "";
}

function openDepartment(name: string) {
  department.value = name;
  view.value = "people";
}

function openGroup(name: string) {
  department.value = GROUP_PREFIX + name;
  view.value = "people";
}

watch([period, department, day], () => {
  person.value = "";
  dashboard.reload();
});

watch([period, department, day, view, person, project], () => {
  router.replace({
    query: {
      period: period.value,
      ...(scope.value.department ? { department: scope.value.department } : {}),
      ...(scope.value.group ? { group: scope.value.group } : {}),
      ...(day.value ? { day: day.value } : {}),
      ...(view.value !== "departments" ? { view: view.value } : {}),
      ...(person.value ? { person: person.value } : {}),
      ...(project.value ? { project: project.value } : {}),
    },
  });
});
</script>
