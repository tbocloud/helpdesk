<template>
  <div class="flex flex-col gap-5">
    <!-- the period and whose leads: kept in the URL, so a view can be shared -->
    <div
      class="flex flex-wrap items-end gap-3"
      role="group"
      :aria-label="__('Period and owner')"
    >
      <div class="overflow-x-auto">
        <TabButtons
          :model-value="period"
          size="md"
          :aria-label="__('Period')"
          :options="PERIODS"
          @update:model-value="setPeriod($event as OverviewPeriod)"
        />
      </div>
      <template v-if="period === 'custom'">
        <FormControl
          v-model="custom.from"
          type="date"
          class="w-40"
          :label="__('From')"
        />
        <FormControl
          v-model="custom.to"
          type="date"
          class="w-40"
          :label="__('To')"
        />
      </template>
      <FormControl
        v-if="data && data.scope !== 'own'"
        v-model="owner"
        type="select"
        class="w-full sm:w-56"
        :label="data.scope === 'team' ? __('Team member') : __('Owner')"
        :options="ownerOptions"
      />
    </div>

    <TaskyState
      v-if="period === 'custom' && !customReady"
      :icon="LucideCalendarRange"
      :title="__('Pick both dates')"
      :message="__('Choose a from and a to date to see that period.')"
    />

    <TaskyState
      v-else-if="overview.error && !data"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the overview')"
      :message="
        errorText(overview.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="overview.reload()" />
    </TaskyState>

    <!-- loading: the tiles' and panels' shape is known -->
    <div
      v-else-if="!data"
      class="flex flex-col gap-5"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div
          v-for="i in 6"
          :key="i"
          class="h-[74px] animate-pulse rounded-xl bg-surface-gray-2"
        />
      </div>
      <div class="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <div class="h-80 animate-pulse rounded-xl bg-surface-gray-2" />
        <div class="h-80 animate-pulse rounded-xl bg-surface-gray-2" />
      </div>
    </div>

    <template v-else>
      <!-- a failed update keeps the last numbers, and says so -->
      <div
        v-if="overview.error"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
          {{
            __(
              "Couldn't update the overview: {0} These numbers may be out of date.",
              errorText(overview.error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="overview.reload()" />
      </div>
      <p class="text-p-sm text-ink-gray-6">
        {{ periodText }}
        <span v-if="overview.loading" class="sr-only" aria-live="polite">{{
          __("Updating")
        }}</span>
      </p>

      <!-- what happened in the period -->
      <section
        class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
        :aria-label="__('This period')"
      >
        <StatTile
          compact
          :label="__('New leads')"
          :value="t.new"
          :icon="LucideUserPlus"
          :to="list('new')"
        />
        <StatTile
          compact
          :label="__('Contacted')"
          :value="t.contacted"
          :icon="LucidePhone"
          :to="list('contacted')"
        />
        <StatTile
          compact
          :label="__('Meetings held')"
          :value="t.meetings"
          :icon="LucideUsers"
          :to="list('meetings')"
        />
        <StatTile
          compact
          :label="__('Proposals sent')"
          :value="t.quotations_sent"
          :icon="LucideFileText"
          :to="list('quotations')"
        />
        <StatTile
          compact
          :label="__('Won')"
          :value="t.won"
          :sub="t.won ? amount(t.won_value) : undefined"
          :icon="LucideTrophy"
          :icon-tone="t.won ? 'success' : 'neutral'"
          :to="list('won')"
        />
        <StatTile
          compact
          :label="__('Lost')"
          :value="t.lost"
          :icon="LucideCircleX"
          :to="list('lost')"
        />
      </section>

      <!-- what needs a person now -->
      <section
        class="grid grid-cols-1 gap-3 sm:grid-cols-3"
        :aria-label="__('Needs attention')"
      >
        <StatTile
          compact
          :label="__('Overdue follow-ups')"
          :value="t.overdue"
          :icon="LucideCalendarX"
          :icon-tone="t.overdue ? 'danger' : 'neutral'"
          :value-tone="t.overdue ? 'danger' : 'neutral'"
          :to="list('overdue', false)"
        />
        <StatTile
          compact
          :label="__('Gone quiet ({0}+ days)', String(data.stale_days))"
          :value="t.stale"
          :icon="LucideHourglass"
          :icon-tone="t.stale ? 'warning' : 'neutral'"
          :to="list('stale', false)"
        />
        <StatTile
          compact
          :label="__('Hot leads')"
          :value="t.hot"
          :icon="LucideFlame"
          :to="list('hot', false)"
        />
      </section>

      <!-- AI runs leads: the day's plan, picked from Call today, follow-ups and hot leads -->
      <section v-if="ai?.enabled" class="panel" :aria-labelledby="ids.plan">
        <header class="panel-head">
          <div class="flex min-w-0 flex-col">
            <h2 :id="ids.plan" class="text-base-medium text-ink-gray-9">
              {{
                owner && data.scope !== "own"
                  ? __("Their plan for today")
                  : __("Your plan for today")
              }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __(
                "Follow-ups due, Call today and hot leads, each with the AI's next step"
              )
            }}</span>
          </div>
          <nav
            class="flex flex-wrap gap-x-3 gap-y-1 text-sm"
            :aria-label="__('What the AI sees')"
          >
            <router-link
              v-for="count in AI_COUNTS"
              :key="count.metric"
              :to="list(count.metric, false)"
              class="num-link font-sans"
              >{{ count.label(ai[count.metric] ?? 0) }}</router-link
            >
          </nav>
        </header>
        <p v-if="!ai.ai_ready" class="px-4 pt-3 text-p-sm text-ink-gray-6">
          {{
            __(
              "The AI isn't set up on the ERP site, so there are no new next steps. Ask an admin to add a provider in TBO Smart Settings."
            )
          }}
        </p>
        <p
          v-if="!ai.plan?.rows.length"
          class="px-4 py-4 text-p-sm text-ink-gray-6"
        >
          {{ __("Nothing due today: no follow-ups and no hot leads waiting.") }}
        </p>
        <ol v-else role="list" class="flex flex-col py-1">
          <li v-for="row in ai.plan.rows" :key="row.name">
            <router-link
              :to="{ name: 'Lead', params: { leadId: row.name } }"
              class="row-link flex flex-col gap-0.5 px-4 py-2.5 sm:flex-row sm:items-center sm:gap-4"
            >
              <span class="flex min-w-0 flex-col sm:w-64 sm:shrink-0">
                <span class="truncate text-sm text-ink-gray-9">{{
                  row.lead_name || row.name
                }}</span>
                <span class="truncate text-xs text-ink-gray-6">{{
                  [row.why, row.tbo_stage].filter(Boolean).join(" · ")
                }}</span>
              </span>
              <span
                class="min-w-0 flex-1 text-sm"
                :class="row.next_action ? 'text-ink-gray-8' : 'text-ink-gray-5'"
              >
                {{ row.next_action || __("No next step from the AI yet") }}
                <span
                  v-if="row.next_action && row.next_due"
                  class="text-xs tabular-nums text-ink-gray-6"
                >
                  · {{ dayjs(row.next_due).format("D MMM") }}</span
                >
              </span>
            </router-link>
          </li>
        </ol>
      </section>

      <div class="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <!-- the pipeline now, stage by stage -->
        <section class="panel" :aria-labelledby="ids.pipeline">
          <header class="panel-head">
            <h2 :id="ids.pipeline" class="text-base-medium text-ink-gray-9">
              {{ __("Pipeline now") }}
            </h2>
            <span class="font-mono text-sm tabular-nums text-ink-gray-7">
              {{ __("{0} open", String(t.open)) }}
              <template v-if="t.open_value">
                · {{ amount(t.open_value) }}</template
              >
            </span>
          </header>
          <ul role="list" class="flex flex-col py-1">
            <li v-for="row in pipeline" :key="row.stage">
              <router-link
                :to="stageLink(row.stage)"
                class="row-link grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-2 sm:grid-cols-[12rem_minmax(0,1fr)_auto]"
              >
                <span class="truncate text-sm text-ink-gray-8">{{
                  row.stage
                }}</span>
                <span
                  class="order-last col-span-2 block h-1.5 overflow-hidden rounded-full bg-surface-gray-2 sm:order-none sm:col-span-1"
                  aria-hidden="true"
                >
                  <span
                    class="block h-full rounded-full bg-surface-gray-7"
                    :style="{ width: `${share(row.count, pipelineMax)}%` }"
                  />
                </span>
                <span
                  class="text-right font-mono text-sm tabular-nums text-ink-gray-9"
                >
                  {{ row.count }}
                  <span
                    v-if="row.value"
                    class="block text-xs text-ink-gray-6 sm:ml-2 sm:inline"
                    >{{ amount(row.value) }}</span
                  >
                </span>
              </router-link>
            </li>
          </ul>
        </section>

        <div class="flex min-w-0 flex-col gap-5">
          <!-- how far this period's new leads got -->
          <section class="panel" :aria-labelledby="ids.funnel">
            <header class="panel-head">
              <h2 :id="ids.funnel" class="text-base-medium text-ink-gray-9">
                {{ __("Funnel") }}
              </h2>
              <span class="text-sm tabular-nums text-ink-gray-7">
                {{ __("{0}% won", String(t.conversion_rate)) }}
              </span>
            </header>
            <p v-if="!t.new" class="px-4 py-4 text-p-sm text-ink-gray-6">
              {{ __("No new leads in this period yet.") }}
            </p>
            <ol v-else class="flex flex-col gap-2 px-4 py-3">
              <li
                v-for="step in data.funnel"
                :key="step.step"
                class="flex flex-col gap-1"
              >
                <div class="flex items-baseline justify-between gap-3 text-sm">
                  <span class="text-ink-gray-8">{{
                    FUNNEL_LABELS[step.step]
                  }}</span>
                  <span class="font-mono tabular-nums text-ink-gray-9">
                    {{ step.count }}
                    <span class="text-xs text-ink-gray-6"
                      >{{ step.rate }}%</span
                    >
                  </span>
                </div>
                <span
                  class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                  aria-hidden="true"
                >
                  <span
                    class="block h-full rounded-full"
                    :class="
                      step.step === 'won' ? 'bg-success' : 'bg-surface-gray-7'
                    "
                    :style="{ width: `${Math.min(step.rate, 100)}%` }"
                  />
                </span>
              </li>
            </ol>
            <p class="px-4 pb-3 text-p-xs text-ink-gray-6">
              {{
                __(
                  "Win rate {0}%: won of the leads closed in this period.",
                  String(t.win_rate)
                )
              }}
            </p>
          </section>

          <!-- why leads were lost -->
          <section class="panel" :aria-labelledby="ids.lost">
            <header class="panel-head">
              <h2 :id="ids.lost" class="text-base-medium text-ink-gray-9">
                {{ __("Why leads were lost") }}
              </h2>
            </header>
            <p
              v-if="!data.lost_reasons.length"
              class="px-4 py-4 text-p-sm text-ink-gray-6"
            >
              {{ __("No leads lost in this period.") }}
            </p>
            <ul v-else role="list" class="flex flex-col py-1">
              <li
                v-for="r in data.lost_reasons.slice(0, 5)"
                :key="r.reason"
                class="flex items-center justify-between gap-3 px-4 py-1.5 text-sm"
              >
                <span class="truncate text-ink-gray-8">{{ r.reason }}</span>
                <span class="font-mono tabular-nums text-ink-gray-9">{{
                  r.count
                }}</span>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <!-- the hottest leads, to call first -->
      <section
        v-if="data.hot.rows.length"
        class="panel"
        :aria-labelledby="ids.hot"
      >
        <header class="panel-head">
          <h2 :id="ids.hot" class="text-base-medium text-ink-gray-9">
            {{ __("Hot leads") }}
          </h2>
          <router-link
            :to="list('hot', false)"
            class="rounded text-sm text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ __("All {0}", String(data.hot.count)) }}
          </router-link>
        </header>
        <ul role="list" class="grid sm:grid-cols-2">
          <li
            v-for="lead in data.hot.rows.slice(0, 6)"
            :key="lead.name"
            class="border-t border-outline-gray-1"
          >
            <router-link
              :to="{ name: 'Lead', params: { leadId: lead.name } }"
              class="row-link flex items-center gap-3 px-4 py-2.5"
            >
              <span class="flex min-w-0 flex-1 flex-col">
                <span class="truncate text-sm text-ink-gray-9">{{
                  lead.lead_name || lead.name
                }}</span>
                <span class="truncate text-xs text-ink-gray-6">
                  {{
                    [lead.organization, lead.status].filter(Boolean).join(" · ")
                  }}
                </span>
              </span>
              <span
                v-if="lead.lead_score != null"
                class="font-mono text-sm tabular-nums text-ink-gray-8"
                :title="__('Lead score')"
              >
                <span class="sr-only">{{ __("Score") }}</span>
                {{ lead.lead_score }}
              </span>
            </router-link>
          </li>
        </ul>
      </section>

      <!-- by owner: who did what this period -->
      <section
        v-if="data.by_owner.length > 1 || data.scope !== 'own'"
        class="panel"
        :aria-labelledby="ids.owners"
      >
        <header class="panel-head">
          <h2 :id="ids.owners" class="text-base-medium text-ink-gray-9">
            {{ __("By owner") }}
          </h2>
        </header>
        <p
          v-if="!data.by_owner.length"
          class="px-4 py-4 text-p-sm text-ink-gray-6"
        >
          {{ __("Nobody has leads in this period yet.") }}
        </p>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[36rem] text-sm">
            <thead>
              <tr class="text-left text-xs text-ink-gray-6">
                <th scope="col" class="px-4 py-2 font-normal">
                  {{ __("Owner") }}
                </th>
                <th
                  v-for="col in OWNER_COLUMNS"
                  :key="col.key"
                  scope="col"
                  class="px-3 py-2 text-right font-normal"
                >
                  {{ col.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in data.by_owner"
                :key="row.user"
                class="border-t border-outline-gray-1"
              >
                <th
                  scope="row"
                  class="max-w-[14rem] truncate px-4 py-2 text-left font-normal text-ink-gray-9"
                >
                  {{ row.full_name }}
                </th>
                <td
                  v-for="col in OWNER_COLUMNS"
                  :key="col.key"
                  class="px-3 py-2 text-right"
                >
                  <router-link
                    :to="ownerLink(row.user, col.metric)"
                    class="num-link"
                    >{{ row[col.key] }}</router-link
                  >
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- segments and sources -->
      <div class="grid gap-5 md:grid-cols-2">
        <section
          v-for="block in BREAKDOWNS"
          :key="block.key"
          class="panel"
          :aria-labelledby="`${ids.prefix}-${block.key}`"
        >
          <header class="panel-head">
            <h2
              :id="`${ids.prefix}-${block.key}`"
              class="text-base-medium text-ink-gray-9"
            >
              {{ block.title }}
            </h2>
            <span class="text-xs text-ink-gray-6">{{
              __("New · Open · Won")
            }}</span>
          </header>
          <p
            v-if="!data[block.key].length"
            class="px-4 py-4 text-p-sm text-ink-gray-6"
          >
            {{ __("No leads to group yet.") }}
          </p>
          <ul v-else role="list" class="flex flex-col py-1">
            <li
              v-for="row in data[block.key]"
              :key="row.value || '-'"
              class="flex items-center gap-3 px-4 py-1.5 text-sm"
            >
              <span
                class="min-w-0 flex-1 truncate"
                :class="row.value ? 'text-ink-gray-8' : 'text-ink-gray-6'"
                >{{ row.value || block.none }}</span
              >
              <template v-if="row.value">
                <router-link
                  :to="fieldLink(block.field, row.value, 'new')"
                  class="num-link w-10 text-right"
                  :aria-label="__('{0} new', String(row.new))"
                  >{{ row.new }}</router-link
                >
                <router-link
                  :to="fieldLink(block.field, row.value, 'open')"
                  class="num-link w-10 text-right"
                  :aria-label="__('{0} open', String(row.open))"
                  >{{ row.open }}</router-link
                >
                <router-link
                  :to="fieldLink(block.field, row.value, 'won')"
                  class="num-link w-10 text-right"
                  :aria-label="__('{0} won', String(row.won))"
                  >{{ row.won }}</router-link
                >
              </template>
              <span
                v-else
                class="font-mono tabular-nums text-ink-gray-7"
                :aria-label="
                  __(
                    '{0} new, {1} open, {2} won',
                    String(row.new),
                    String(row.open),
                    String(row.won)
                  )
                "
                >{{ row.new }} · {{ row.open }} · {{ row.won }}</span
              >
            </li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, useId, watch } from "vue";
import { useRoute, useRouter, type RouteLocationRaw } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideFileText from "~icons/lucide/file-text";
import LucideFlame from "~icons/lucide/flame";
import LucideHourglass from "~icons/lucide/hourglass";
import LucidePhone from "~icons/lucide/phone";
import LucideTrophy from "~icons/lucide/trophy";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideUsers from "~icons/lucide/users";
import type { LeadMetric, LeadOverview, OverviewPeriod } from "./leads";

const PERIODS: { value: OverviewPeriod; label: string }[] = [
  { value: "week", label: __("This week") },
  { value: "month", label: __("This month") },
  { value: "quarter", label: __("This quarter") },
  { value: "custom", label: __("Custom") },
];
const FUNNEL_LABELS: Record<LeadOverview["funnel"][number]["step"], string> = {
  created: __("Came in"),
  contacted: __("Contacted"),
  meeting: __("Meeting"),
  proposal: __("Proposal"),
  won: __("Won"),
};
const OWNER_COLUMNS: {
  key:
    | "new"
    | "contacted"
    | "meetings_held"
    | "quotations_sent"
    | "won"
    | "open";
  label: string;
  metric: LeadMetric;
}[] = [
  { key: "new", label: __("New"), metric: "new" },
  { key: "contacted", label: __("Contacted"), metric: "contacted" },
  { key: "meetings_held", label: __("Meetings"), metric: "meetings" },
  { key: "quotations_sent", label: __("Proposals"), metric: "quotations" },
  { key: "won", label: __("Won"), metric: "won" },
  { key: "open", label: __("Open"), metric: "open" },
];
const AI_COUNTS: {
  metric: "high_intent" | "unhappy" | "stage_suggested";
  label: (n: number) => string;
}[] = [
  { metric: "high_intent", label: (n) => __("{0} high intent", String(n)) },
  { metric: "unhappy", label: (n) => __("{0} unhappy", String(n)) },
  {
    metric: "stage_suggested",
    label: (n) => __("{0} stage moves to check", String(n)),
  },
];
const BREAKDOWNS = [
  {
    key: "by_segment" as const,
    field: "segment" as const,
    title: __("By segment"),
    none: __("No segment"),
  },
  {
    key: "by_source" as const,
    field: "source" as const,
    title: __("By source"),
    none: __("No source"),
  },
];

const route = useRoute();
const router = useRouter();
const ids = {
  prefix: useId(),
  pipeline: useId(),
  funnel: useId(),
  lost: useId(),
  hot: useId(),
  owners: useId(),
  plan: useId(),
};

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const period = computed<OverviewPeriod>(() => {
  const value = queryValue("period");
  return PERIODS.some((p) => p.value === value)
    ? (value as OverviewPeriod)
    : "month";
});
const custom = reactive({ from: queryValue("from"), to: queryValue("to") });
const customReady = computed(
  () => !!custom.from && !!custom.to && custom.from <= custom.to
);
const owner = computed({
  get: () => queryValue("owner"),
  set: (value: string) => setQuery({ owner: value || undefined }),
});

function setQuery(query: Record<string, string | undefined>) {
  router.replace({ query: { ...route.query, ...query } });
}

function setPeriod(value: OverviewPeriod) {
  setQuery({ period: value === "month" ? undefined : value });
}

watch(
  () => ({ ...custom }),
  (c) => setQuery({ from: c.from || undefined, to: c.to || undefined })
);

const overview = createResource({
  url: "helpdesk.api.leads.get_overview",
  makeParams: () => ({
    period: period.value,
    from_date: period.value === "custom" ? custom.from : null,
    to_date: period.value === "custom" ? custom.to : null,
    owner: owner.value || null,
  }),
});

watch(
  [period, owner, () => customReady.value && `${custom.from}:${custom.to}`],
  () => {
    if (period.value !== "custom" || customReady.value) overview.reload();
  },
  { immediate: true }
);

defineExpose({ reload: () => overview.reload() });

const data = computed(() => overview.data as LeadOverview | undefined);
const t = computed(() => data.value!.totals);
const ai = computed(() => data.value?.ai);

const ownerOptions = computed(() => [
  {
    label: data.value?.scope === "team" ? __("My team") : __("Everyone"),
    value: "",
  },
  ...(data.value?.people ?? []).map((p) => ({
    label: p.full_name,
    value: p.user,
  })),
]);

const periodText = computed(() => {
  const d = data.value!;
  const from = dayjs(d.from_date);
  const to = dayjs(d.to_date);
  const range = from.isSame(to, "year")
    ? `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`
    : `${from.format("D MMM YYYY")} – ${to.format("D MMM YYYY")}`;
  const whose =
    d.scope === "own"
      ? __("your leads")
      : owner.value
      ? d.people.find((p) => p.user === owner.value)?.full_name || owner.value
      : d.scope === "team"
      ? __("your team's leads")
      : __("everyone's leads");
  return __("{0}, {1}. Every number opens its leads.", range, whose);
});

// open stages, then won and lost: the pipeline reads left to right
const pipeline = computed(() =>
  (data.value?.pipeline ?? []).filter(
    (row) => row.count || !["Won", "Lost"].includes(row.type)
  )
);
const pipelineMax = computed(() =>
  Math.max(...pipeline.value.map((row) => row.count), 1)
);

function share(part: number, whole: number) {
  return whole ? Math.round((part / whole) * 100) : 0;
}

function amount(value: number) {
  const currency = data.value?.currency;
  return currency ? money(value, currency) : String(value);
}

/** The list of the leads behind one number. `inPeriod` false for today's state. */
function list(metric: LeadMetric, inPeriod = true): RouteLocationRaw {
  return {
    name: "Leads",
    query: {
      view: "all",
      metric,
      ...(inPeriod ? periodQuery() : {}),
      owner: owner.value || undefined,
    },
  };
}

function periodQuery() {
  return {
    period: period.value,
    from: period.value === "custom" ? custom.from : undefined,
    to: period.value === "custom" ? custom.to : undefined,
  };
}

function stageLink(stage: string): RouteLocationRaw {
  return {
    name: "Leads",
    query: { view: "all", stage, owner: owner.value || undefined },
  };
}

function ownerLink(user: string, metric: LeadMetric): RouteLocationRaw {
  return {
    name: "Leads",
    query: {
      view: "all",
      owner: user,
      metric,
      ...(metric === "open" ? {} : periodQuery()),
    },
  };
}

function fieldLink(
  field: "segment" | "source",
  value: string,
  metric?: LeadMetric
): RouteLocationRaw {
  return {
    name: "Leads",
    query: {
      view: "all",
      [field]: value,
      owner: owner.value || undefined,
      ...(metric
        ? { metric, ...(metric === "open" ? {} : periodQuery()) }
        : {}),
    },
  };
}
</script>

<style scoped>
.panel {
  @apply min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base;
}
.panel-head {
  @apply flex flex-wrap items-baseline justify-between gap-2 border-b border-outline-gray-1 px-4 py-3;
}
.row-link {
  @apply transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4;
}
.num-link {
  @apply inline-block rounded font-mono tabular-nums text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4;
}
</style>
