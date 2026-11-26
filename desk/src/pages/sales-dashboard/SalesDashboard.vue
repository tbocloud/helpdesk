<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Dashboard')"
      :subtitle="
        __('Your calls, leads and targets today, live from the ERP site.')
      "
    >
      <template #right-header>
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
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="dash.error && !data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load your dashboard')"
          :message="
            errorText(dash.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Try again')" @click="refresh" />
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
          <!-- who and where: the day, the running slot and the way into the calls -->
          <section
            class="flex flex-wrap items-center justify-between gap-4 rounded-xl bg-brand p-4 text-brand-on md:p-5"
            :aria-label="__('Today')"
          >
            <div class="flex min-w-0 items-center gap-3">
              <PersonAvatar :name="auth.userName" size="xl" />
              <div class="flex min-w-0 flex-col gap-1">
                <p class="text-xs opacity-80 tabular-nums">
                  {{ dayjs(now).format("dddd, D MMMM YYYY") }}
                  <template v-if="department"> · {{ department }}</template>
                </p>
                <h2 class="text-xl font-bold">
                  {{ greeting(dayjs(now)) }}, {{ firstName }}
                </h2>
                <p
                  v-if="batch"
                  class="flex flex-wrap items-center gap-1.5 text-xs font-medium"
                >
                  <span
                    class="inline-flex items-center gap-1 rounded-full bg-black/20 px-2 py-0.5 tabular-nums"
                  >
                    <LucideClock class="size-3" aria-hidden="true" />
                    {{
                      __(
                        "{0} slot · {1}",
                        batch.slot,
                        timeLeftText(secondsLeft)
                      )
                    }}
                  </span>
                  <span
                    class="rounded-full bg-surface-base px-2 py-0.5 text-ink-gray-9 tabular-nums"
                  >
                    {{
                      __(
                        "{0} calls left in this slot",
                        String(calls?.counts?.pending ?? 0)
                      )
                    }}
                  </span>
                </p>
                <p v-else-if="calls?.next_slot" class="text-xs opacity-90">
                  {{
                    __(
                      "Next slot: {0} at {1}",
                      calls.next_slot.label,
                      dayjs(calls.next_slot.starts_at).format("h:mm a")
                    )
                  }}
                </p>
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <RouterLink
                v-if="canFindProspects"
                :to="{ name: 'FindProspects' }"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-black/20 px-3 text-sm font-medium hover:bg-black/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                {{ __("Find prospects") }}
              </RouterLink>
              <RouterLink
                v-if="calls?.enabled"
                :to="startCalling"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-surface-base px-3 text-sm font-medium text-ink-gray-9 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                <LucidePhone class="size-4" aria-hidden="true" />
                {{ __("Start calling") }}
              </RouterLink>
            </div>
          </section>

          <!-- the day's calls and the open leads -->
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          >
            <template v-if="calls?.enabled">
              <StatTile
                :label="__('Calls today')"
                :value="today.called"
                :icon="LucidePhone"
                :sub="
                  __(
                    '{0} still to call · goal {1}',
                    String(stillToCall),
                    String(goal)
                  )
                "
              >
                <Sparkline
                  v-if="week"
                  :values="mySeries.called"
                  color="--brand"
                />
              </StatTile>
              <StatTile
                :label="__('Contacted')"
                :value="today.connected"
                :icon="LucideCheck"
                icon-tone="success"
                :sub="__('People you actually spoke to')"
              >
                <Sparkline
                  v-if="week"
                  :values="mySeries.contacted"
                  color="--success"
                />
              </StatTile>
              <StatTile
                :label="__('Contact rate')"
                :value="`${percent(today.connected, today.called)}%`"
                :icon="LucidePercent"
                :sub="__('Contacted ÷ called, today')"
              >
                <Sparkline v-if="week" :values="rateSeries" color="--violet" />
              </StatTile>
            </template>
            <StatTile
              v-if="month"
              :label="__('Open leads')"
              :value="month.totals.open"
              :icon="LucideTrendingUp"
              :sub="
                month.totals.won === 1
                  ? __('1 won this month')
                  : __('{0} won this month', String(month.totals.won))
              "
              :to="{ name: 'Leads', query: { view: 'mine' } }"
            />
          </div>
          <p
            v-if="calls && !calls.enabled"
            class="rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3 text-sm text-ink-gray-7"
          >
            {{
              calls.reason ||
              __(
                "Your department doesn't hand out daily call batches, so there are no calls to count today."
              )
            }}
          </p>
          <PartError :message="errors.calls" />

          <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <!-- Today's calls: how far through the day's plan -->
            <section
              v-if="calls?.enabled"
              class="flex min-w-0 flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="ids.calls"
            >
              <header class="flex items-center justify-between gap-3">
                <h2
                  :id="ids.calls"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Today's calls") }}
                </h2>
                <CardLink :to="{ name: 'Leads', query: { view: 'today' } }">
                  {{ __("Details") }}
                </CardLink>
              </header>
              <div class="flex flex-wrap items-center gap-6">
                <DonutChart
                  :parts="dayParts"
                  :value="today.called"
                  :caption="__('of {0}', String(goal))"
                  :label="__('Today\'s calls')"
                />
                <dl class="flex min-w-[10rem] flex-1 flex-col gap-2.5">
                  <div
                    v-for="row in dayLegend"
                    :key="row.label"
                    class="flex items-center gap-2 text-sm"
                  >
                    <span
                      class="size-2.5 shrink-0 rounded-full"
                      :style="{ background: cssColor(row.color) }"
                      aria-hidden="true"
                    />
                    <dt class="flex-1 text-ink-gray-7">{{ row.label }}</dt>
                    <dd class="font-semibold tabular-nums text-ink-gray-9">
                      {{ row.value }}
                    </dd>
                  </div>
                </dl>
              </div>
              <p
                class="flex items-center justify-between rounded-lg bg-success-soft px-3 py-2 text-sm text-success"
              >
                <span>{{ __("Contact rate today") }}</span>
                <b class="tabular-nums">
                  {{ percent(today.connected, today.called) }}%
                </b>
              </p>
            </section>

            <MyTargetsCard v-if="auth.hasSalesTargets" />

            <!-- My pipeline: the person's open leads by stage -->
            <section
              v-if="month"
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="ids.pipeline"
            >
              <header class="flex items-start justify-between gap-3">
                <div class="flex flex-col gap-0.5">
                  <h2
                    :id="ids.pipeline"
                    class="text-base font-semibold text-ink-gray-9"
                  >
                    {{ __("My pipeline") }}
                  </h2>
                  <p class="text-xs tabular-nums text-ink-gray-6">
                    {{ __("{0} open leads, by stage", String(pipelineTotal)) }}
                  </p>
                </div>
                <CardLink :to="{ name: 'Leads', query: { view: 'mine' } }">
                  {{ __("My leads") }}
                </CardLink>
              </header>
              <p
                v-if="!pipeline.length"
                class="py-6 text-center text-sm text-ink-gray-6"
              >
                {{ __("No open leads right now.") }}
              </p>
              <ul v-else class="flex flex-col gap-2">
                <li v-for="row in pipeline" :key="row.stage">
                  <RouterLink
                    :to="{
                      name: 'Leads',
                      query: { view: 'mine', stage: row.stage },
                    }"
                    class="grid grid-cols-[minmax(6rem,9rem)_1fr_2.5rem] items-center gap-3 rounded-md py-1 text-sm hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  >
                    <span class="truncate text-ink-gray-8">{{
                      row.stage
                    }}</span>
                    <span class="h-5 overflow-hidden rounded bg-surface-gray-2">
                      <span
                        class="flex h-full items-center rounded bg-brand px-1.5 text-2xs font-semibold text-brand-on tabular-nums"
                        :style="{
                          width: `${Math.max(
                            (row.count / pipelineMax) * 100,
                            4
                          )}%`,
                        }"
                        >{{ row.count }}</span
                      >
                    </span>
                    <span
                      class="text-right text-xs tabular-nums text-ink-gray-6"
                      >{{ percent(row.count, pipelineTotal) }}%</span
                    >
                  </RouterLink>
                </li>
              </ul>
            </section>
            <PartError :message="errors.month" />

            <!-- Calls this week: called and contacted each day since Monday -->
            <section
              v-if="week"
              class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="ids.week"
            >
              <h2
                :id="ids.week"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Calls this week") }}
              </h2>
              <WeekLineChart
                :days="week.days"
                :series="[
                  {
                    name: __('Called'),
                    values: mySeries.called,
                    color: '--brand',
                  },
                  {
                    name: __('Contacted'),
                    values: mySeries.contacted,
                    color: '--success',
                  },
                ]"
                :label="__('Calls this week')"
                area
              />
              <p
                class="flex items-center justify-between border-t border-outline-gray-1 pt-3 text-sm text-ink-gray-6"
              >
                {{ __("Total this week") }}
                <b class="tabular-nums text-ink-gray-9">
                  {{ __("{0} calls", String(total(mySeries.called))) }}
                </b>
              </p>
            </section>
            <PartError :message="errors.week" />

            <!-- How today's calls ended: where the called leads stand now -->
            <section
              v-if="calls?.enabled"
              class="flex min-w-0 flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="ids.ended"
            >
              <div class="flex flex-col gap-0.5">
                <h2
                  :id="ids.ended"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("How today's calls ended") }}
                </h2>
                <p class="text-xs tabular-nums text-ink-gray-6">
                  {{ __("All {0} calls made today", String(today.called)) }}
                </p>
              </div>
              <p
                v-if="!endings.length"
                class="py-6 text-center text-sm text-ink-gray-6"
              >
                {{ __("No calls made yet today.") }}
              </p>
              <div v-else class="flex flex-wrap items-center gap-6">
                <DonutChart
                  :parts="endings"
                  :value="today.called"
                  :caption="__('calls')"
                  :label="__('How today\'s calls ended')"
                />
                <dl class="flex min-w-[12rem] flex-1 flex-col gap-2">
                  <div
                    v-for="row in endings"
                    :key="row.label"
                    class="flex items-center gap-2 text-sm"
                  >
                    <span
                      class="size-2.5 shrink-0 rounded-full"
                      :style="{ background: cssColor(row.color) }"
                      aria-hidden="true"
                    />
                    <dt class="flex-1 text-ink-gray-7">{{ row.label }}</dt>
                    <dd class="font-semibold tabular-nums text-ink-gray-9">
                      {{ row.value }}
                    </dd>
                    <dd
                      class="w-10 text-right text-xs tabular-nums text-ink-gray-6"
                    >
                      {{ percent(row.value, endingsTotal) }}%
                    </dd>
                  </div>
                </dl>
              </div>
            </section>

            <!-- Up next to call: the queue, pending first, then the overdue -->
            <section
              v-if="calls?.enabled"
              class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="ids.next"
            >
              <header
                class="flex items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-3"
              >
                <h2
                  :id="ids.next"
                  class="flex items-center gap-2 text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Up next to call") }}
                  <span
                    class="rounded-full bg-surface-gray-10 px-2 py-0.5 text-xs text-ink-base tabular-nums"
                    >{{ queue.length }}</span
                  >
                </h2>
                <CardLink :to="{ name: 'Leads', query: { view: 'today' } }">
                  {{ __("See all") }}
                </CardLink>
              </header>
              <p
                v-if="!queue.length"
                class="px-4 py-8 text-center text-sm text-ink-gray-6"
              >
                {{ __("Nothing left to call right now.") }}
              </p>
              <ul v-else class="divide-y divide-outline-gray-1">
                <li
                  v-for="call in queue.slice(0, NEXT_ROWS)"
                  :key="call.item"
                  class="flex items-center gap-3 px-4 py-3"
                >
                  <PersonAvatar
                    :name="call.summary.lead_name || call.lead"
                    size="lg"
                    neutral
                  />
                  <div class="flex min-w-0 flex-1 flex-col">
                    <span
                      class="flex items-center gap-1.5 truncate text-sm font-semibold text-ink-gray-9"
                    >
                      {{ call.summary.lead_name || call.lead }}
                      <span
                        v-if="isOverdue(call)"
                        class="rounded-full bg-danger-soft px-1.5 py-0.5 text-2xs font-medium text-danger"
                        >{{ __("Overdue") }}</span
                      >
                    </span>
                    <span class="truncate text-xs text-ink-gray-6">
                      {{
                        [call.summary.district, call.summary.phone]
                          .filter(Boolean)
                          .join(" · ")
                      }}
                    </span>
                  </div>
                  <RouterLink
                    :to="{
                      name: 'Lead',
                      params: { leadId: call.lead },
                      query: { item: call.item },
                    }"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-sm font-medium text-brand-on hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                    :aria-label="
                      __('Call {0}', call.summary.lead_name || call.lead)
                    "
                  >
                    <LucidePhone class="size-3.5" aria-hidden="true" />
                    {{ __("Call") }}
                  </RouterLink>
                </li>
              </ul>
            </section>

            <!-- Follow-ups: the first ones due, with the AI's next step when it has one -->
            <section
              v-if="followUps"
              class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base lg:col-span-2"
              :aria-labelledby="ids.followUps"
            >
              <header
                class="flex items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-3"
              >
                <h2
                  :id="ids.followUps"
                  class="flex items-center gap-2 text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Follow-ups") }}
                  <span
                    v-if="followUps.counts.overdue"
                    class="inline-flex items-center gap-1 rounded-full bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger tabular-nums"
                  >
                    <LucideAlarmClock class="size-3" aria-hidden="true" />
                    {{ __("{0} overdue", String(followUps.counts.overdue)) }}
                  </span>
                </h2>
                <CardLink :to="{ name: 'Leads', query: { view: 'follow_up' } }">
                  {{ __("See all") }}
                </CardLink>
              </header>
              <p
                v-if="!followUps.rows.length"
                class="px-4 py-8 text-center text-sm text-ink-gray-6"
              >
                {{ __("No follow-ups due. Nice.") }}
              </p>
              <ul v-else class="divide-y divide-outline-gray-1">
                <li v-for="lead in followUps.rows" :key="lead.name">
                  <RouterLink
                    :to="{ name: 'Lead', params: { leadId: lead.name } }"
                    class="flex items-center gap-3 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                  >
                    <PersonAvatar
                      :name="lead.lead_name || lead.name"
                      size="lg"
                      neutral
                    />
                    <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span class="flex flex-wrap items-center gap-1.5">
                        <span
                          class="truncate text-sm font-semibold text-ink-gray-9"
                          >{{ lead.lead_name || lead.name }}</span
                        >
                        <span
                          v-if="lead.tbo_stage"
                          class="rounded-full px-2 py-0.5 text-2xs font-medium"
                          :class="
                            stagePillClass(leadOptions.data, lead.tbo_stage)
                          "
                          >{{ lead.tbo_stage }}</span
                        >
                      </span>
                      <span
                        v-if="nextStep(lead.name)"
                        class="flex items-center gap-1 truncate text-xs text-ink-gray-6"
                      >
                        <LucideSparkles
                          class="size-3 shrink-0"
                          aria-hidden="true"
                        />
                        {{ nextStep(lead.name) }}
                      </span>
                    </div>
                    <span
                      v-if="lead.next_follow_up"
                      class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
                      :class="
                        isPast(lead.next_follow_up)
                          ? 'bg-danger-soft text-danger'
                          : 'bg-info-soft text-info'
                      "
                    >
                      {{
                        isPast(lead.next_follow_up)
                          ? __(
                              "Since {0}",
                              dayjs(lead.next_follow_up).format("D MMM")
                            )
                          : __(
                              "Due {0}",
                              dayjs(lead.next_follow_up).format("D MMM")
                            )
                      }}
                    </span>
                  </RouterLink>
                </li>
              </ul>
            </section>
            <PartError :message="errors.follow_ups" />
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
import {
  stageColors,
  timeLeftText,
  type QueueCall,
} from "@/pages/leads/callBatches";
import {
  leadOptions,
  loadLeadOptions,
  stagePillClass,
} from "@/pages/leads/leads";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucidePercent from "~icons/lucide/percent";
import LucidePhone from "~icons/lucide/phone";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideTrendingUp from "~icons/lucide/trending-up";
import CardLink from "./CardLink.vue";
import DonutChart, { type DonutPart } from "./DonutChart.vue";
import MyTargetsCard from "./MyTargetsCard.vue";
import PartError from "./PartError.vue";
import {
  cssColor,
  greeting,
  openStages,
  percent,
  total,
  useLiveRead,
  type MyDashboard,
} from "./salesDashboard";
import Sparkline from "./Sparkline.vue";
import WeekLineChart from "./WeekLineChart.vue";

const NEXT_ROWS = 3;
const auth = useAuthStore();
loadLeadOptions();
const ids = {
  calls: useId(),
  pipeline: useId(),
  week: useId(),
  ended: useId(),
  next: useId(),
  followUps: useId(),
};

// when the answer came, so the slot's time left counts down between reads
const readAt = ref(Date.now());
const dash = createResource<MyDashboard>({
  url: "helpdesk.api.sales_dashboard.get_my_dashboard",
  auto: true,
  onSuccess: () => (readAt.value = Date.now()),
});
function refresh() {
  dash.submit({ fresh: 1 });
}
// the calls move all day: read them again every two minutes (the rest is cached a minute)
useLiveRead(dash);
const now = ref(Date.now());
useIntervalFn(() => (now.value = Date.now()), 30_000);

const data = computed(() => dash.data);
const errors = computed(() => data.value?.errors ?? {});
const calls = computed(() => data.value?.calls ?? null);
const month = computed(() => data.value?.month ?? null);
const week = computed(() => data.value?.week ?? null);
const followUps = computed(() => data.value?.follow_ups ?? null);

const firstName = computed(() => (auth.userName || "").split(" ")[0]);
const batch = computed(() => calls.value?.batch ?? null);
const department = computed(
  () => batch.value?.department || calls.value?.focus?.department || ""
);
const secondsLeft = computed(
  () =>
    (batch.value?.seconds_left ?? 0) -
    Math.floor((now.value - readAt.value) / 1000)
);
const canFindProspects = computed(
  () => !!leadOptions.data?.can_find_prospects && !leadOptions.data?.is_bd
);

const today = computed(() => ({
  size: 0,
  called: 0,
  connected: 0,
  stages: [],
  ...calls.value?.today,
}));
// the day's goal: the plan's calls across the slots, or what was handed out when more
const goal = computed(() =>
  Math.max(
    today.value.size,
    (calls.value?.slots ?? []).reduce((sum, slot) => sum + slot.planned, 0)
  )
);
const stillToCall = computed(() =>
  Math.max(goal.value - today.value.called, 0)
);
const callBacks = computed(
  () =>
    today.value.stages?.find((row) => row.stage === "Follow-up Required")
      ?.count ?? 0
);

const dayLegend = computed(() => [
  { label: __("Called"), value: today.value.called, color: "--brand" },
  { label: __("Contacted"), value: today.value.connected, color: "--success" },
  { label: __("Call backs"), value: callBacks.value, color: "--warm-fill" },
  {
    label: __("Still to call"),
    value: stillToCall.value,
    color: "--outline-gray-3",
  },
]);
// the ring is the day's goal: called against still to call
const dayParts = computed<DonutPart[]>(() => [
  dayLegend.value[0],
  dayLegend.value[3],
]);

const stageColor = computed(() =>
  stageColors((today.value.stages ?? []).map((row) => row.stage))
);
const endings = computed<DonutPart[]>(() =>
  (today.value.stages ?? [])
    .filter((row) => row.count > 0)
    .map((row) => ({
      label: row.stage,
      value: row.count,
      color: stageColor.value(row.stage),
    }))
);
const endingsTotal = computed(() => total(endings.value.map((p) => p.value)));

// the person's own line of the week; today's point is the live count of Today's calls
const mySeries = computed(() => {
  const days = week.value?.days ?? [];
  const mine = week.value?.people[0];
  const called = days.map((_d, i) => mine?.called[i] ?? 0);
  const contacted = days.map((_d, i) => mine?.contacted[i] ?? 0);
  if (calls.value?.enabled && days.length) {
    called[days.length - 1] = today.value.called;
    contacted[days.length - 1] = today.value.connected;
  }
  return { called, contacted };
});
const rateSeries = computed(() =>
  mySeries.value.called.map((called, i) =>
    percent(mySeries.value.contacted[i], called)
  )
);

const pipeline = computed(() => openStages(month.value?.pipeline ?? []));
const pipelineTotal = computed(() =>
  total(pipeline.value.map((row) => row.count))
);
const pipelineMax = computed(() =>
  Math.max(...pipeline.value.map((row) => row.count), 1)
);

const queue = computed<QueueCall[]>(() => [
  ...(calls.value?.pending ?? []),
  ...(calls.value?.overdue ?? []),
]);
const isOverdue = (call: QueueCall) =>
  (calls.value?.overdue ?? []).some((c) => c.item === call.item);
const startCalling = computed(() => {
  const first = queue.value[0];
  return first
    ? {
        name: "Lead",
        params: { leadId: first.lead },
        query: { item: first.item },
      }
    : { name: "Leads", query: { view: "today" } };
});

const isPast = (day: string) => dayjs(day).isBefore(dayjs(), "day");
function nextStep(lead: string) {
  return month.value?.plan.find((row) => row.name === lead)?.next_action || "";
}
</script>
