<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Sales team dashboard')"
      :subtitle="
        __('How your team\'s leads are moving, and who needs a nudge.')
      "
    >
      <template #right-header>
        <div class="flex items-center gap-2">
          <Button
            size="md"
            :aria-label="__('Refresh')"
            :loading="dash.loading"
            @click="refresh"
          >
            <template #icon>
              <LucideRefreshCw class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-if="auth.canAssignSalesTargets"
            size="md"
            :label="__('Set targets')"
            :route="{ name: 'SalesTargets' }"
          />
          <Button
            v-if="canAssign"
            size="md"
            variant="solid"
            :label="__('Assign leads')"
            :route="{ name: 'AssignLeads' }"
          >
            <template #prefix>
              <LucideSend class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </template>
    </LayoutHeader>

    <div class="cc-page relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <!-- the period, whose leads, the department and the source, in one card -->
        <div
          class="cc-card flex flex-wrap items-center justify-between gap-3 px-4 py-3"
          :style="accentStyle('blue')"
        >
          <div class="flex flex-wrap items-center gap-3">
            <TabButtons
              :model-value="period"
              size="md"
              :aria-label="__('Period')"
              :options="PERIODS"
              @update:model-value="setQuery({ period: $event })"
            />
            <label class="sr-only" :for="ownerId">{{
              __("Whose leads")
            }}</label>
            <FormControl
              :id="ownerId"
              type="select"
              class="sm:w-52"
              :model-value="owner"
              :options="ownerOptions"
              @update:model-value="setQuery({ owner: $event || undefined })"
            />
            <FormControl
              v-if="departmentOptions.length"
              type="select"
              class="sm:w-48"
              :aria-label="__('Department')"
              :model-value="department"
              :options="departmentOptions"
              @update:model-value="
                setQuery({ department: $event || undefined })
              "
            />
            <FormControl
              type="select"
              class="sm:w-44"
              :aria-label="__('Source')"
              :model-value="source"
              :options="sourceOptions"
              @update:model-value="setQuery({ source: $event || undefined })"
            />
          </div>
          <p class="text-[12px] text-ink-gray-6">
            <strong class="font-mono font-semibold text-ink-gray-9">{{
              dayjs().format("ddd, D MMM YYYY")
            }}</strong>
            · {{ __("tap any number to open those leads") }}
          </p>
        </div>

        <TaskyState
          v-if="dash.error && !data"
          class="cc-card py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('This dashboard is for managers')
              : __('Couldn\'t load the team dashboard')
          "
          :message="
            errorText(dash.error, __('Check your connection and try again.'))
          "
        >
          <Button v-if="!isRefusal" :label="__('Try again')" @click="refresh" />
        </TaskyState>

        <template v-else-if="!data">
          <div
            v-for="n in 3"
            :key="n"
            class="h-40 animate-pulse rounded-xl bg-surface-gray-3"
            aria-busy="true"
            :aria-label="__('Loading')"
          />
        </template>

        <template v-else>
          <RevenueHero
            :currency="currency"
            :period-label="periodLabel"
            :won-value="totals.won_value ?? 0"
            :won-count="totals.won"
            :unpriced="totals.won_unpriced ?? 0"
            :previous="previousWon"
            :target="wonTarget"
            :money="data.money"
            :money-note="moneyNote"
            :podium="podium"
            :shows-podium="!owner"
            @open="openWon"
          />

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <div class="flex min-w-0 flex-col gap-4 lg:col-span-3">
              <!-- a running month carried to its end at today's rate -->
              <CcCard
                v-if="forecast"
                accent="orange"
                :icon="LucideHourglass"
                :title="__('Forecasted revenue')"
              >
                <template v-if="wonTarget" #actions>
                  <span
                    class="cc-pill rounded-md px-1.5 py-0.5 text-[11px] font-bold tabular-nums"
                    >{{ percent(forecast.forecast, wonTarget) }}%</span
                  >
                </template>
                <p
                  class="cc-ink cc-glow font-mono text-[26px] font-bold leading-tight tabular-nums"
                  :title="fullAmount(forecast.forecast, currency)"
                >
                  {{ shortAmount(forecast.forecast, currency) }}
                </p>
                <p class="-mt-2 text-xs text-ink-gray-6">
                  {{ __("month-end at today's rate") }}
                </p>
                <dl class="grid grid-cols-2 gap-3 text-xs">
                  <div :style="accentStyle('green')">
                    <dt class="text-[10px] font-bold uppercase text-ink-gray-6">
                      {{ __("Daily rate") }}
                    </dt>
                    <dd class="cc-ink font-mono font-semibold tabular-nums">
                      {{ shortAmount(forecast.perDay, currency) }}/{{
                        __("day")
                      }}
                    </dd>
                  </div>
                  <div v-if="forecast.needed" :style="accentStyle('red')">
                    <dt class="text-[10px] font-bold uppercase text-ink-gray-6">
                      {{ __("Required rate") }}
                    </dt>
                    <dd class="cc-ink font-mono font-semibold tabular-nums">
                      {{ shortAmount(forecast.needed, currency) }}/{{
                        __("day")
                      }}
                    </dd>
                  </div>
                </dl>
              </CcCard>

              <!-- the open stages that hold leads, with what each is worth -->
              <CcCard
                accent="blue"
                :icon="LucideFilter"
                :title="__('Active pipeline stages')"
                :sub="
                  __(
                    '{0} open leads worth {1}',
                    String(pipelineTotal),
                    shortAmount(pipelineValue, currency)
                  )
                "
              >
                <p
                  v-if="!pipeline.length"
                  class="py-6 text-center text-sm text-ink-gray-6"
                >
                  {{ __("No open leads.") }}
                </p>
                <ul v-else class="flex flex-col gap-1.5">
                  <li v-for="row in pipeline" :key="row.stage">
                    <RouterLink
                      :to="stageLink(row.stage)"
                      class="flex flex-col gap-1 rounded px-1 py-0.5 text-sm hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                    >
                      <span class="flex items-center gap-2">
                        <span
                          class="flex-1 truncate font-semibold text-ink-gray-8"
                          >{{ row.stage }}
                          <span class="font-normal text-ink-gray-5"
                            >({{ row.count.toLocaleString() }})</span
                          ></span
                        >
                        <span
                          class="cc-ink font-mono text-xs font-semibold tabular-nums"
                          :style="accentStyle('green')"
                          :title="fullAmount(row.value ?? 0, currency)"
                        >
                          {{ shortAmount(row.value ?? 0, currency) }}
                        </span>
                      </span>
                      <span
                        class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                        aria-hidden="true"
                      >
                        <span
                          class="cc-fill block h-full rounded-full"
                          :style="{
                            width: `${percent(row.count, pipelineMax)}%`,
                          }"
                        />
                      </span>
                    </RouterLink>
                  </li>
                </ul>
              </CcCard>
            </div>

            <!-- Team calls this week: each person's calls per day -->
            <CcCard
              class="lg:col-span-6"
              accent="cyan"
              :icon="LucidePhoneCall"
              :title="__('Team calls this week')"
              :sub="
                weekLines.length < weekPeople.length
                  ? __(
                      'Calls per day, the {0} who called most',
                      String(weekLines.length)
                    )
                  : __('Calls per day, person by person')
              "
            >
              <PartError :message="errors.week" />
              <p
                v-if="week && !weekLines.length"
                class="py-10 text-center text-sm text-ink-gray-6"
              >
                {{ __("No calls this week yet.") }}
              </p>
              <WeekLineChart
                v-else-if="week"
                :days="week.days"
                :series="weekLines"
                :label="__('Team calls this week')"
                height="h-72"
                area
              />
            </CcCard>

            <div class="min-w-0 lg:col-span-3">
              <PeriodCompare
                v-if="data.previous"
                class="h-full"
                :now="totals"
                :before="data.previous.totals"
                :period-label="periodLabel"
                :range="rangeText(data.previous)"
                :currency="currency"
              />
              <PartError
                v-else-if="errors.previous"
                :message="errors.previous"
              />
            </div>
          </div>

          <!-- the number cards -->
          <div
            class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
          >
            <CcStat v-for="stat in stats" :key="stat.label" v-bind="stat" />
          </div>

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <!-- Lead funnel: how the period's new leads moved on -->
            <CcCard
              class="lg:col-span-7"
              accent="violet"
              :icon="LucideFilter"
              :title="__('Lead funnel')"
            >
              <template #actions>
                <CardLink :to="{ name: 'Leads', query: { view: 'overview' } }">
                  {{ __("Full overview") }}
                </CardLink>
              </template>
              <ol class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
                <li
                  v-for="(step, index) in funnel"
                  :key="step.step"
                  :style="accentStyle(FUNNEL_ACCENTS[index])"
                >
                  <RouterLink
                    :to="metricLink(step.metric, periodQuery)"
                    class="cc-soft flex h-full flex-col gap-1.5 rounded-lg p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  >
                    <span
                      class="text-[10px] font-bold uppercase tracking-[0.06em]"
                      >{{ step.label }}</span
                    >
                    <span
                      class="cc-glow font-mono text-xl font-bold tabular-nums text-ink-gray-9"
                      >{{ step.count }}</span
                    >
                    <span
                      class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                    >
                      <span
                        class="cc-fill block h-full rounded-full"
                        :style="{
                          width: `${
                            index ? step.share : step.count ? 100 : 0
                          }%`,
                        }"
                      />
                    </span>
                    <span class="text-2xs tabular-nums text-ink-gray-6">{{
                      index
                        ? __(
                            "{0}% of {1}",
                            String(step.share),
                            funnel[index - 1].label.toLowerCase()
                          )
                        : periodWord.came
                    }}</span>
                  </RouterLink>
                </li>
              </ol>
              <p
                v-if="biggestDrop"
                class="cc-pill flex items-start gap-2 rounded-lg px-3 py-2 text-sm"
                :style="accentStyle('red')"
              >
                <LucideTriangleAlert
                  class="mt-0.5 size-4 shrink-0"
                  aria-hidden="true"
                />
                {{ biggestDrop }}
              </p>
            </CcCard>

            <!-- the open stages as upright bars -->
            <CcCard
              class="lg:col-span-5"
              accent="amber"
              :icon="LucideChartColumn"
              :title="__('Stage pipeline')"
              :sub="__('Open leads in each stage; tap a bar for its leads')"
            >
              <template #actions>
                <span
                  class="cc-pill rounded-md px-2 py-0.5 text-xs font-semibold"
                  >{{ __("Stages") }}</span
                >
              </template>
              <p
                v-if="!pipeline.length"
                class="py-10 text-center text-sm text-ink-gray-6"
              >
                {{ __("No open leads.") }}
              </p>
              <StageBars
                v-else
                :rows="pipeline"
                :currency="currency"
                :label="__('Open leads in each stage')"
                :link="stageLink"
              />
            </CcCard>
          </div>

          <TeamLeaderboard
            :title="__('Sales executive performance & target leaderboard')"
            :calls-label="periodWord.calls"
            :rows="leaderRows"
            :error="errors.people"
            :currency="currency"
            :month-name="hasTargets ? monthTitle(monthValue()) : ''"
            :leads-query="narrowQuery"
          />

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <!-- Calls this week, ranked -->
            <CcCard
              accent="green"
              :icon="LucidePhone"
              :title="__('Calls this week')"
              :sub="__('Leaderboard')"
            >
              <p
                v-if="!leaderboard.length"
                class="py-8 text-center text-sm text-ink-gray-6"
              >
                {{ __("No calls this week yet.") }}
              </p>
              <ol v-else class="flex flex-col gap-3">
                <li
                  v-for="(row, index) in leaderboard"
                  :key="row.user"
                  class="flex items-center gap-3"
                >
                  <span
                    class="cc-pill grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold tabular-nums"
                    >{{ index + 1 }}</span
                  >
                  <PersonAvatar :name="row.full_name" />
                  <span class="flex min-w-0 flex-1 flex-col gap-1">
                    <span
                      class="flex items-center justify-between gap-2 text-sm"
                    >
                      <span class="truncate font-semibold text-ink-gray-9">{{
                        row.full_name
                      }}</span>
                      <b class="cc-ink font-mono tabular-nums">{{
                        row.calls
                      }}</b>
                    </span>
                    <span
                      class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                    >
                      <span
                        class="cc-fill block h-full rounded-full"
                        :style="{
                          width: `${percent(row.calls, leaderboard[0].calls)}%`,
                        }"
                      />
                    </span>
                  </span>
                </li>
              </ol>
            </CcCard>

            <!-- Leads handed out today, by slot -->
            <CcCard
              accent="violet"
              :icon="LucideSend"
              :title="__('Leads handed out today')"
            >
              <template v-if="canAssign" #actions>
                <CardLink :to="{ name: 'AssignLeads' }">
                  {{ __("Assign") }}
                </CardLink>
              </template>
              <PartError :message="errors.handed_out" />
              <p v-if="source && handedOut" class="text-xs text-ink-gray-6">
                {{ __("All sources: batches aren't counted by source.") }}
              </p>
              <p
                v-if="handedOut && !handedOut.length"
                class="py-8 text-center text-sm text-ink-gray-6"
              >
                {{ __("No call batches handed out yet today.") }}
              </p>
              <ul
                v-else-if="handedOut"
                class="divide-y divide-[color:var(--cc-card-border)]"
              >
                <li
                  v-for="slot in handedOut"
                  :key="`${slot.slot}-${slot.department}`"
                  class="grid grid-cols-[minmax(7rem,9rem)_1fr_4.5rem] items-center gap-3 py-2.5 text-sm"
                  :style="
                    accentStyle(slot.called >= slot.size ? 'green' : 'violet')
                  "
                >
                  <span class="truncate">
                    <b class="text-ink-gray-9">{{ slot.slot }}</b>
                    <span class="text-ink-gray-6">
                      · {{ slot.department }}</span
                    >
                  </span>
                  <span
                    class="block h-2 overflow-hidden rounded-full bg-surface-gray-2"
                  >
                    <span
                      class="cc-fill block h-full rounded-full"
                      :style="{ width: `${percent(slot.called, slot.size)}%` }"
                    />
                  </span>
                  <span class="text-right text-xs tabular-nums text-ink-gray-7">
                    <b class="cc-ink font-mono"
                      >{{ slot.called }} / {{ slot.size }}</b
                    >
                    {{ __("called") }}
                  </span>
                </li>
              </ul>
            </CcCard>

            <!-- Needs a nudge: what is waiting on a person -->
            <CcCard
              accent="red"
              :icon="LucideBellRing"
              :title="__('Needs a nudge')"
            >
              <RouterLink
                :to="metricLink('overdue', ownerQuery)"
                class="cc-pill flex items-center gap-3 rounded-lg px-3 py-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                <LucideAlarmClock class="size-4 shrink-0" aria-hidden="true" />
                <span class="flex-1">
                  <b class="font-mono tabular-nums">{{ totals.overdue }}</b>
                  {{ __("follow-ups overdue") }}
                </span>
                <span class="font-medium">{{ __("Open") }} →</span>
              </RouterLink>
              <RouterLink
                :to="metricLink('stale', ownerQuery)"
                class="cc-pill flex items-center gap-3 rounded-lg px-3 py-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                :style="accentStyle('amber')"
              >
                <LucideMoon class="size-4 shrink-0" aria-hidden="true" />
                <span class="flex-1">
                  <b class="font-mono tabular-nums">{{ totals.stale }}</b>
                  {{
                    __(
                      "leads gone quiet ({0}+ days)",
                      String(overview.stale_days)
                    )
                  }}
                </span>
                <span class="font-medium">{{ __("Re-engage") }} →</span>
              </RouterLink>
              <div v-if="overview.ai.enabled" class="flex flex-wrap gap-1.5">
                <RouterLink
                  v-for="chip in aiChips"
                  :key="chip.metric"
                  :to="metricLink(chip.metric, ownerQuery)"
                  class="cc-pill rounded-full px-2.5 py-1 text-xs font-medium tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  :style="accentStyle(chip.accent)"
                >
                  {{ chip.label }}
                </RouterLink>
              </div>
            </CcCard>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import {
  fullAmount,
  rangeText,
  shortAmount,
} from "@/pages/leads/business/businessFormat";
import {
  choices,
  leadOptions,
  loadLeadOptions,
  usableDepartments,
  type LeadOptions,
} from "@/pages/leads/leads";
import { useChartColors } from "@/pages/performance/chartTheme";
import {
  monthPace,
  monthTitle,
  monthValue,
  overallOf,
  type Progress,
  type TeamTargets,
} from "@/pages/sales-targets/salesTargets";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, type Component, useId, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBellRing from "~icons/lucide/bell-ring";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileText from "~icons/lucide/file-text";
import LucideFilter from "~icons/lucide/filter";
import LucideFlame from "~icons/lucide/flame";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideIndianRupee from "~icons/lucide/indian-rupee";
import LucideLock from "~icons/lucide/lock";
import LucideMoon from "~icons/lucide/moon";
import LucidePercent from "~icons/lucide/percent";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneCall from "~icons/lucide/phone-call";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSend from "~icons/lucide/send";
import LucideTarget from "~icons/lucide/target";
import LucideTrendingUp from "~icons/lucide/trending-up";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideTrophy from "~icons/lucide/trophy";
import LucideUsers from "~icons/lucide/users";
import LucideWallet from "~icons/lucide/wallet";
import CardLink from "./CardLink.vue";
import CcCard from "./CcCard.vue";
import CcStat from "./CcStat.vue";
import PartError from "./PartError.vue";
import PeriodCompare from "./PeriodCompare.vue";
import RevenueHero, { type PodiumPerson } from "./RevenueHero.vue";
import StageBars from "./StageBars.vue";
import {
  accentStyle,
  forecastOf,
  metricLink,
  openStages,
  percent,
  total,
  useLiveRead,
  type Accent,
  type TeamDashboard,
  type TeamPeriod,
} from "./salesDashboard";
import TeamLeaderboard, { type LeaderRow } from "./TeamLeaderboard.vue";
import WeekLineChart, { type WeekLine } from "./WeekLineChart.vue";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const colors = useChartColors();
const ownerId = useId();
loadLeadOptions();

const PERIODS = [
  { label: __("Today"), value: "today" },
  { label: __("This week"), value: "week" },
  { label: __("This month"), value: "month" },
];

// the period, the person, the department and the source are in the URL, so a link or a
// reload opens the same view
const period = computed<TeamPeriod>(() =>
  ["today", "week", "month"].includes(String(route.query.period))
    ? (route.query.period as TeamPeriod)
    : "today"
);
const owner = computed(() => String(route.query.owner || ""));
const department = computed(() => String(route.query.department || ""));
const source = computed(() => String(route.query.source || ""));
function setQuery(query: Record<string, string | undefined>) {
  router.replace({ query: { ...route.query, ...query } });
}
function params() {
  return {
    period: period.value,
    owner: owner.value || null,
    department: department.value || null,
    source: source.value || null,
  };
}

const dash = createResource<TeamDashboard>({
  url: "helpdesk.api.sales_dashboard.get_team_dashboard",
  makeParams: params,
  auto: true,
});
// a new filter drops the read on its way: only the latest answer is wanted
watch([period, owner, department, source], () => {
  dash.abort();
  dash.reload();
});
function refresh() {
  dash.submit({ ...params(), fresh: 1 });
}
const isRefusal = computed(() => dash.error?.exc_type === "PermissionError");

const data = computed(() => dash.data);
const overview = computed(() => data.value!.overview);
const totals = computed(() => overview.value.totals);
const errors = computed(() => data.value?.errors ?? {});
const people = computed(() => data.value?.people ?? null);
const week = computed(() => data.value?.week ?? null);
const handedOut = computed(() => data.value?.handed_out ?? null);

const canAssign = computed(
  () =>
    !!leadOptions.data?.departments?.some(
      (d: { call_batches_enabled?: boolean }) => d.call_batches_enabled
    )
);

const periodWord = computed(
  () =>
    ({
      today: {
        came: __("came in today"),
        team: __("Your team today"),
        calls: __("Calls today"),
        sent: __("sent today"),
        word: __("today"),
      },
      week: {
        came: __("came in this week"),
        team: __("Your team this week"),
        calls: __("Calls this week"),
        sent: __("sent this week"),
        word: __("this week"),
      },
      month: {
        came: __("came in this month"),
        team: __("Your team this month"),
        calls: __("Calls this month"),
        sent: __("sent this month"),
        word: __("this month"),
      },
    }[period.value])
);
// the Leads list opens with the same department, source, period and person; today's state
// needs no period
const narrowQuery = computed(() => ({
  department: department.value || undefined,
  source: source.value || undefined,
}));
const ownerQuery = computed(() => ({
  ...narrowQuery.value,
  owner: owner.value || undefined,
}));
const periodQuery = computed(() => ({
  ...ownerQuery.value,
  period: period.value,
}));
function stageLink(stage: string) {
  return {
    name: "Leads",
    query: { view: "all", stage, ...ownerQuery.value },
  };
}

const options = computed(() => leadOptions.data as LeadOptions | undefined);
// no picker for one department or none: there is nothing to choose between
const departmentOptions = computed(() => {
  const list = usableDepartments(options.value, department.value);
  return list.length > 1
    ? [
        { label: __("Any department"), value: "" },
        ...list.map((d) => ({ label: d.name, value: d.name })),
      ]
    : [];
});
const sourceOptions = computed(() =>
  choices(options.value?.sources, __("Any source"))
);

const ownerOptions = computed(() => [
  {
    label: __(
      "Everyone · {0} people",
      String(data.value?.overview.people.length ?? 0)
    ),
    value: "",
  },
  ...(data.value?.overview.people ?? []).map((p) => ({
    label: p.full_name,
    value: p.user,
  })),
]);

// every open stage that holds leads, in the ERP site's order, with what it is worth
const pipeline = computed(() => openStages(overview.value.pipeline));
const pipelineTotal = computed(() => total(pipeline.value.map((p) => p.count)));
const pipelineValue = computed(() =>
  total(pipeline.value.map((p) => p.value ?? 0))
);
const pipelineMax = computed(() =>
  Math.max(0, ...pipeline.value.map((p) => p.count))
);

// each person's line, coloured by their place in the team list so a filter never repaints them
const weekPeople = computed(() =>
  (week.value?.people ?? []).filter((p) => total(p.called) > 0)
);
const weekLines = computed<WeekLine[]>(() =>
  [...weekPeople.value]
    .sort((a, b) => total(b.called) - total(a.called))
    .slice(0, colors.value.series.length)
    .map((p) => {
      const place = (week.value?.people ?? []).findIndex(
        (q) => q.user === p.user
      );
      return {
        name: p.full_name,
        values: p.called,
        color: colors.value.series[place % colors.value.series.length],
      };
    })
);
const leaderboard = computed(() =>
  (week.value?.people ?? [])
    .map((p) => ({
      user: p.user,
      full_name: p.full_name,
      calls: total(p.called),
    }))
    .filter((p) => p.calls > 0)
    .sort((a, b) => b.calls - a.calls)
);

const FUNNEL_ACCENTS: Accent[] = ["blue", "cyan", "violet", "amber", "green"];
const FUNNEL_STEPS: Record<string, { label: string; metric: string }> = {
  created: { label: __("New leads"), metric: "new" },
  contacted: { label: __("Contacted"), metric: "contacted" },
  meeting: { label: __("Meetings held"), metric: "meetings" },
  proposal: { label: __("Proposals sent"), metric: "quotations" },
  won: { label: __("Won"), metric: "won" },
};
const funnel = computed(() =>
  overview.value.funnel
    .filter((row) => row.step in FUNNEL_STEPS)
    .map((row, index, rows) => ({
      ...row,
      ...FUNNEL_STEPS[row.step],
      share: index ? percent(row.count, rows[index - 1].count) : 100,
    }))
);
// the step where most leads are lost, said in words
const biggestDrop = computed(() => {
  let worst: { from: string; to: string; count: number; of: number } | null =
    null;
  funnel.value.forEach((step, index) => {
    if (!index) return;
    const before = funnel.value[index - 1];
    if (!before.count) return;
    if (!worst || step.count / before.count < worst.count / worst.of)
      worst = {
        from: before.label.toLowerCase(),
        to: step.label.toLowerCase(),
        count: step.count,
        of: before.count,
      };
  });
  if (!worst) return "";
  const { from, to, count, of } = worst as {
    from: string;
    to: string;
    count: number;
    of: number;
  };
  return __(
    "Biggest drop: {0} of {1} {2} reached {3}.",
    String(count),
    String(of),
    from,
    to
  );
});

const aiChips = computed(() => {
  const ai = overview.value.ai;
  return [
    {
      metric: "high_intent",
      label: __("{0} high intent", String(ai.high_intent ?? 0)),
      accent: "orange" as Accent,
    },
    {
      metric: "unhappy",
      label: __("{0} unhappy", String(ai.unhappy ?? 0)),
      accent: "red" as Accent,
    },
    {
      metric: "stage_suggested",
      label: __("{0} stage moves to check", String(ai.stage_suggested ?? 0)),
      accent: "blue" as Accent,
    },
  ];
});

// targets: a Sales Head sees each person's month, counted as the Sales targets page counts it
const hasTargets = computed(
  () => auth.canAssignSalesTargets && !!teamTargets.data
);
const teamTargets = createResource<TeamTargets>({
  url: "helpdesk.api.sales_targets.get_team",
  params: { month: monthValue() },
  auto: auth.canAssignSalesTargets,
});
const teamProgress = createResource<Record<string, Progress>>({
  url: "helpdesk.api.sales_targets.get_team_progress",
  params: { month: monthValue() },
  auto: auth.canAssignSalesTargets,
});
// the day moves on: read again every two minutes, and leave nothing running on the way out
useLiveRead(dash, teamTargets, teamProgress);
const targets = computed(() => {
  const team = teamTargets.data;
  const progress = teamProgress.data;
  const byUser: Record<string, { percent: number | null; behind: number }> = {};
  if (!team || !progress) return byUser;
  for (const person of team.people) {
    const counted = progress[person.user];
    if (person.target && counted?.state === "counted")
      byUser[person.user] = overallOf(person.target, counted, team.currency);
  }
  return byUser;
});
const targetOf = (user: string) => targets.value[user];

// the money: the ERP site's currency, whichever part says it
const currency = computed(
  () =>
    overview.value.currency ||
    data.value?.money?.currency ||
    teamTargets.data?.currency ||
    ""
);
const periodLabel = computed(
  () => PERIODS.find((p) => p.value === period.value)!.label
);
const previousWon = computed(() => {
  const before = data.value?.previous;
  return before
    ? { value: before.totals.won_value ?? 0, won: before.totals.won ?? 0 }
    : null;
});
const moneyNote = computed(() => {
  if (department.value || source.value)
    return __(
      "Collections aren't counted by department or source, so they're left out while one is picked."
    );
  return errors.value.money || "";
});
// the month's won value target: the person's, or the sales team's summed (the people on
// this page: targets set for anyone else, a test account, would inflate it)
const wonTarget = computed(() => {
  const team = teamTargets.data;
  if (period.value !== "month" || !team) return null;
  const shown = new Set(overview.value.people.map((p) => p.user));
  const sum = total(
    team.people
      .filter((p) => (owner.value ? p.user === owner.value : shown.has(p.user)))
      .flatMap((p) => p.target?.criteria ?? [])
      .filter((c) => c.measure === "won_value" && typeof c.target === "number")
      .map((c) => c.target as number)
  );
  return sum || null;
});

// people level on won value and deals share a place (1, 2, 2, 4)
function rankBy<T>(rows: T[], key: (row: T) => string) {
  return rows.map((row, index) => {
    let rank = index + 1;
    while (rank > 1 && key(rows[rank - 2]) === key(row)) rank--;
    return { row, rank };
  });
}
const podium = computed<PodiumPerson[]>(() =>
  rankBy(
    (data.value?.revenue ?? []).filter((r) => r.won > 0),
    (r) => `${r.won_value}:${r.won}`
  ).map(({ row, rank }) => ({ ...row, rank }))
);
function openWon(user: string) {
  router.push(metricLink("won", { ...periodQuery.value, owner: user }));
}

// a running month carried to its end at today's rate
const forecast = computed(() => {
  if (period.value !== "month") return null;
  const pace = monthPace(monthValue());
  if (pace.state !== "running") return null;
  return forecastOf(totals.value.won_value ?? 0, wonTarget.value, pace);
});

// the number cards, in the mockup's colours: each figure keeps its colour and its icon
const stats = computed(() => {
  const t = totals.value;
  const c = currency.value;
  const money = data.value?.money;
  const list: {
    label: string;
    value: string | number;
    title?: string;
    icon: Component;
    accent: Accent;
    sub?: string;
    to?: ReturnType<typeof metricLink>;
  }[] = [
    {
      label: __("Total leads"),
      value: t.new,
      icon: LucideUsers,
      accent: "blue",
      sub: periodWord.value.came,
      to: metricLink("new", periodQuery.value),
    },
    {
      label: __("Active pipeline"),
      value: t.open,
      icon: LucideTrendingUp,
      accent: "violet",
      sub: __("worth {0}", shortAmount(t.open_value ?? 0, c)),
      to: metricLink("open", ownerQuery.value),
    },
    {
      label: __("Hot leads"),
      value: t.hot,
      icon: LucideFlame,
      accent: "red",
      sub: __("ready to close"),
      to: metricLink("hot", ownerQuery.value),
    },
    {
      label: __("Contacted"),
      value: t.contacted,
      icon: LucidePhone,
      accent: "cyan",
      sub: __("{0}% of new leads", String(percent(t.contacted, t.new))),
      to: metricLink("contacted", periodQuery.value),
    },
    {
      label: __("Proposals sent"),
      value: t.quotations_sent,
      icon: LucideFileText,
      accent: "amber",
      sub: money
        ? __("worth {0}", shortAmount(money.proposals_value, c))
        : periodWord.value.sent,
      to: metricLink("quotations", periodQuery.value),
    },
    {
      label: __("Converted (won)"),
      value: t.won,
      icon: LucideTrophy,
      accent: "green",
      sub: t.won_unpriced
        ? __("{0} of them without an amount", String(t.won_unpriced))
        : __("worth {0}", shortAmount(t.won_value ?? 0, c)),
      to: metricLink("won", periodQuery.value),
    },
    {
      label: __("Conversion ratio"),
      value: `${t.conversion_rate ?? 0}%`,
      icon: LucidePercent,
      accent: "green",
      sub: __(
        "of new leads won · win rate {0}%",
        String(Math.round(t.win_rate))
      ),
    },
  ];
  if (wonTarget.value)
    list.push({
      label: __("Sales target"),
      value: shortAmount(wonTarget.value, c),
      title: fullAmount(wonTarget.value, c),
      icon: LucideTarget,
      accent: "blue",
      sub:
        (t.won_value ?? 0) >= wonTarget.value
          ? __("reached")
          : __(
              "{0} to go",
              shortAmount(wonTarget.value - (t.won_value ?? 0), c)
            ),
    });
  if (money)
    list.push(
      {
        label: __("Revenue received"),
        value: shortAmount(money.advances, c),
        title: fullAmount(money.advances, c),
        icon: LucideIndianRupee,
        accent: "green",
        sub: __("received {0}", periodWord.value.word),
      },
      {
        label: __("Total receivables"),
        value: shortAmount(money.to_collect, c),
        title: fullAmount(money.to_collect, c),
        icon: LucideWallet,
        accent: "violet",
        sub: __("outstanding now"),
      },
      {
        label: __("Payments overdue"),
        value: shortAmount(money.overdue, c),
        title: fullAmount(money.overdue, c),
        icon: LucideCircleAlert,
        accent: "red",
        sub: __("past their due date, now"),
      }
    );
  list.push({
    label: __("Overdue follow-ups"),
    value: t.overdue,
    icon: LucideAlarmClock,
    accent: "orange",
    sub: __("{0} more gone quiet", String(t.stale)),
    to: metricLink("overdue", ownerQuery.value),
  });
  return list;
});

// the leaderboard: each salesperson's calls, their leads' progress and what they won
const leaderRows = computed<LeaderRow[] | null>(() => {
  if (!people.value) return null;
  const leads = new Map(overview.value.by_owner.map((r) => [r.user, r]));
  const won = new Map((data.value?.revenue ?? []).map((r) => [r.user, r]));
  // everyone with calls or with leads: someone who only held meetings has no call row
  const calls = new Map(people.value.map((p) => [p.user, p]));
  const noCalls = { given: 0, called: 0, contacted: 0, calls: 0, missed: 0 };
  const everyone = [
    ...people.value,
    ...overview.value.by_owner
      .filter((o) => !calls.has(o.user))
      .map((o) => ({
        ...noCalls,
        user: o.user,
        full_name: o.full_name,
        talk_seconds: 0,
      })),
  ];
  const rows = everyone.map((p) => {
    const own = leads.get(p.user);
    const deals = own?.won ?? null;
    // one person picked: the overview is theirs alone; else only winners were read
    const wonValue = owner.value
      ? totals.value.won_value ?? null
      : won.get(p.user)?.won_value ?? (deals === 0 ? 0 : null);
    return {
      user: p.user,
      full_name: p.full_name,
      given: p.given,
      called: p.called,
      contacted: p.contacted,
      // per answered call; the call log may record calls without talk time, which isn't 0s
      talkPerCall:
        p.talk_seconds && p.calls > p.missed
          ? Math.round(p.talk_seconds / (p.calls - p.missed))
          : null,
      meetings: own?.meetings_held ?? null,
      proposals: own?.quotations_sent ?? null,
      won: deals,
      wonValue,
      target: targetOf(p.user),
    };
  });
  rows.sort(
    (a, b) =>
      (b.wonValue ?? -1) - (a.wonValue ?? -1) ||
      (b.won ?? -1) - (a.won ?? -1) ||
      b.contacted - a.contacted ||
      b.called - a.called
  );
  return rankBy(
    rows,
    (r) => `${r.wonValue}:${r.won}:${r.contacted}:${r.called}`
  ).map(({ row, rank }) => ({ ...row, rank }));
});
</script>
