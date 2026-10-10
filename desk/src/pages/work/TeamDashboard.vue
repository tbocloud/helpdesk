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
              "Who finished what, on time, and who is champion. Scores come from work delivered by its due date; hours count only a little."
            )
          }}
        </p>

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
            <ChampionCard
              :title="championTitle"
              :period="periodMeta.label"
              :champion="data?.champion ?? null"
              :loading="!data"
            />
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
                v-bind="change('tasks')"
              />
              <StatTile
                :label="__('On time')"
                :value="pctText(data?.summary.on_time_pct)"
                :icon="LucideCalendarCheck"
                icon-tone="success"
                :loading="!data"
                v-bind="change('on_time_pct', ' pts')"
              />
              <StatTile
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
              <TabButtons
                v-model="view"
                class="self-start"
                size="md"
                :aria-label="__('Show')"
                :options="VIEWS.map((v) => ({ label: v.label, value: v.key }))"
              />

              <div
                v-if="!data"
                class="h-64 animate-pulse rounded-lg bg-surface-gray-2"
              />
              <TeamDepartmentList
                v-else-if="view === 'departments'"
                :departments="data.departments"
                @open="openDepartment"
              />
              <TeamPeopleList
                v-else-if="view === 'people'"
                :people="data.people"
                :open="person"
                @toggle="person = $event"
              />
              <TeamProjectList
                v-else
                :projects="data.projects"
                :highlight="project"
              />
            </div>

            <!-- trend, analysis and this year's champions -->
            <aside class="flex min-w-0 flex-col gap-4">
              <TeamAnalysis
                v-if="data"
                :analysis="data.analysis"
                :period="period"
                :department="data.department"
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
import { pctText } from "@/pages/performance/performanceMeta";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Avatar,
  Button,
  createResource,
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
import TeamAnalysis from "./components/TeamAnalysis.vue";
import TeamDepartmentList from "./components/TeamDepartmentList.vue";
import TeamPeopleList from "./components/TeamPeopleList.vue";
import TeamProjectList from "./components/TeamProjectList.vue";
import TeamTrendChart from "./components/TeamTrendChart.vue";
import {
  delta,
  historyLabel,
  hoursText,
  PERIODS,
  rangeText,
  VIEWS,
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
const department = ref(query("department"));
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
    department: department.value || null,
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
    ...access.departments.map((d) => ({ label: d, value: d })),
  ];
});

const championTitle = computed(() => {
  const scope = data.value?.department;
  return scope ? __("{0} champion", scope) : __("Champion");
});
const historyNote = computed(() =>
  data.value?.department
    ? __("{0}, kept when each period ends.", data.value.department)
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

function openDepartment(name: string) {
  department.value = name;
  view.value = "people";
}

watch([period, department], () => {
  person.value = "";
  dashboard.reload();
});

watch([period, department, view, person, project], () => {
  router.replace({
    query: {
      period: period.value,
      ...(department.value ? { department: department.value } : {}),
      ...(view.value !== "departments" ? { view: view.value } : {}),
      ...(person.value ? { person: person.value } : {}),
      ...(project.value ? { project: project.value } : {}),
    },
  });
});
</script>
