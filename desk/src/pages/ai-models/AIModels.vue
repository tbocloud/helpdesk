<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("AI models") }}</h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="loading"
          @click="load()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <TabButtons
            :model-value="view"
            :options="views"
            :aria-label="__('View')"
            @update:model-value="go({ view: $event })"
          />
          <TabButtons
            :model-value="String(days)"
            :options="periods"
            :aria-label="__('Period')"
            @update:model-value="go({ days: $event })"
          />
        </div>

        <p
          v-if="error"
          role="alert"
          class="flex flex-wrap items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          {{ errorText(error, __("Couldn't read the AI models.")) }}
          <Button
            variant="ghost"
            size="sm"
            :label="__('Retry')"
            @click="load()"
          />
        </p>

        <div
          v-if="loading && !shown"
          class="h-64 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          :aria-label="__('Loading')"
        />

        <!-- 1. every model side by side -->
        <template v-else-if="view === 'models' && overview">
          <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              :label="__('AI spend, {0} days', String(overview.days))"
              :value="money(overview.totals.cost)"
              :sub="
                overview.budget_usd
                  ? __('monthly budget {0}', money(overview.budget_usd))
                  : ''
              "
            />
            <StatTile
              :label="__('Calls')"
              :value="overview.totals.calls.toLocaleString()"
              :sub="__('{0} models', String(usedModels))"
            />
            <StatTile
              :label="__('Error rate')"
              :value="pct(overview.totals.error_rate)"
              :sub="__('{0} failed calls', String(overview.totals.failed))"
            />
            <StatTile
              :label="__('Needs attention')"
              :value="String(overview.attention.length)"
              :sub="overview.attention.join(', ') || __('all models healthy')"
            />
          </div>

          <p
            v-if="!overview.totals.calls"
            class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
          >
            {{ __("No AI calls in this period.") }}
          </p>

          <div class="overflow-x-auto rounded-xl border border-outline-gray-2">
            <table class="w-full min-w-[60rem] text-p-sm">
              <thead>
                <tr class="bg-surface-gray-1 text-left text-ink-gray-5">
                  <th scope="col" class="px-4 py-2.5 font-medium">
                    {{ __("Model") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Calls") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Cost") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Speed (median / slow)") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Errors") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Ran as fallback") }}
                  </th>
                  <th scope="col" class="px-4 py-2.5 font-medium">
                    {{ __("Status") }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in overview.models"
                  :key="m.model"
                  class="border-t border-outline-gray-1 align-top"
                >
                  <td class="px-4 py-3">
                    <button
                      type="button"
                      class="rounded text-left text-base-medium text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      @click="go({ view: 'model', model: m.model })"
                    >
                      {{ m.model }}
                    </button>
                    <div class="text-ink-gray-5">{{ m.provider }}</div>
                    <div class="text-ink-gray-5">{{ usedFor(m.used_for) }}</div>
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ m.calls.toLocaleString() }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ money(m.cost) }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ speed(m.p50, m.p95) }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ pct(m.error_rate) }}
                    <div class="text-ink-gray-5">{{ m.failed }}</div>
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ pct(m.fallback_rate) }}
                  </td>
                  <td class="px-4 py-3">
                    <Badge
                      :label="__(m.status)"
                      :theme="STATUS_THEME[m.status] || 'gray'"
                      size="sm"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <SectionCard :title="__('Cost by model')">
              <BarList
                class="px-4 pb-4"
                :rows="bars(overview.models, 'cost', (v) => money(v))"
              />
            </SectionCard>
            <SectionCard :title="__('Error rate by model')">
              <BarList
                class="px-4 pb-4"
                :rows="
                  bars(overview.models, 'error_rate', (v) => pct(v), 'danger')
                "
              />
            </SectionCard>
          </div>
          <p v-if="overview.recorded_since" class="text-p-xs text-ink-gray-5">
            {{
              __(
                "Speed and errors are recorded since {0}; earlier calls show cost only.",
                overview.recorded_since
              )
            }}
          </p>
        </template>

        <!-- 2. one model -->
        <template v-else-if="view === 'model'">
          <div class="flex flex-wrap items-end gap-3">
            <div class="w-full sm:w-72">
              <FormControl
                type="select"
                :label="__('Model')"
                :model-value="model"
                :options="modelOptions"
                @update:model-value="go({ model: $event })"
              />
            </div>
            <template v-if="detail">
              <Badge
                :label="__(detail.status)"
                :theme="STATUS_THEME[detail.status] || 'gray'"
                size="md"
              />
              <span class="text-p-sm text-ink-gray-5">
                {{ detail.provider }} · {{ usedFor(detail.used_for) }}
              </span>
            </template>
            <TabButtons
              class="ml-auto"
              :model-value="tab"
              :options="tabs"
              :aria-label="__('Analysis')"
              @update:model-value="go({ tab: $event })"
            />
          </div>

          <p v-if="!model" class="text-p-sm text-ink-gray-6">
            {{ __("Choose a model.") }}
          </p>
          <template v-else-if="detail">
            <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                :label="__('Calls')"
                :value="detail.calls.toLocaleString()"
              />
              <StatTile :label="__('Cost')" :value="money(detail.cost)" />
              <StatTile
                :label="__('Speed (median)')"
                :value="seconds(detail.p50)"
                :sub="__('slow end {0}', seconds(detail.p95))"
              />
              <StatTile
                :label="__('Error rate')"
                :value="pct(detail.error_rate)"
                :sub="__('{0} failed calls', String(detail.failed))"
              />
            </div>

            <p
              v-if="!detail.calls"
              class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
            >
              {{ __("No calls to this model in this period.") }}
            </p>

            <template v-else-if="tab === 'performance'">
              <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <SectionCard :title="__('Cost per day (USD)')">
                  <WeekLineChart
                    class="px-4 pb-4"
                    :days="dayLabels"
                    :series="[line(__('Cost'), 'cost')]"
                    :label="__('Cost per day')"
                    area
                  />
                </SectionCard>
                <SectionCard :title="__('Calls per day')">
                  <WeekLineChart
                    class="px-4 pb-4"
                    :days="dayLabels"
                    :series="[line(__('Calls'), 'calls')]"
                    :label="__('Calls per day')"
                    area
                  />
                </SectionCard>
                <SectionCard :title="__('Speed by job (median)')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(detail.by_job, 'p50', (v) => seconds(v), '', 'name')
                    "
                  />
                </SectionCard>
                <SectionCard :title="__('Cost by job')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(detail.by_job, 'cost', (v) => money(v), '', 'name')
                    "
                  />
                </SectionCard>
              </div>
              <SectionCard :title="__('Slowest calls')">
                <div class="overflow-x-auto px-4 pb-4">
                  <table class="w-full min-w-[28rem] text-p-sm">
                    <thead>
                      <tr class="text-left text-ink-gray-5">
                        <th scope="col" class="py-1.5 pr-3 font-medium">
                          {{ __("When") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Job") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Ticket") }}
                        </th>
                        <th
                          scope="col"
                          class="py-1.5 pl-3 text-right font-medium"
                        >
                          {{ __("Seconds") }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, i) in detail.slowest"
                        :key="i"
                        class="border-t border-outline-gray-1"
                      >
                        <td class="py-1.5 pr-3">{{ row.when }}</td>
                        <td class="px-3 py-1.5">{{ row.job || "-" }}</td>
                        <td class="px-3 py-1.5">
                          <RouterLink
                            v-if="row.ticket"
                            :to="{
                              name: 'TicketAgent',
                              params: { ticketId: row.ticket },
                            }"
                            class="underline underline-offset-2"
                          >
                            #{{ row.ticket }}
                          </RouterLink>
                          <span v-else>-</span>
                        </td>
                        <td class="py-1.5 pl-3 text-right tabular-nums">
                          {{ row.seconds }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </SectionCard>
            </template>

            <template v-else>
              <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <SectionCard :title="__('Error rate per day (%)')">
                  <WeekLineChart
                    class="px-4 pb-4"
                    :days="dayLabels"
                    :series="[line(__('Error rate'), 'error_rate')]"
                    :label="__('Error rate per day')"
                  />
                </SectionCard>
                <SectionCard :title="__('Errors by type')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(
                        detail.errors_by_kind,
                        'count',
                        (v) => String(v),
                        'danger',
                        'kind'
                      )
                    "
                    :empty="__('No errors in this period.')"
                  />
                </SectionCard>
                <SectionCard :title="__('Errors by job')">
                  <BarList
                    class="px-4 pb-4"
                    :rows="
                      bars(
                        detail.errors_by_job,
                        'failed',
                        (v) => String(v),
                        'danger',
                        'name'
                      )
                    "
                    :empty="__('No errors in this period.')"
                  />
                </SectionCard>
              </div>
              <SectionCard :title="__('Latest errors')">
                <div class="overflow-x-auto px-4 pb-4">
                  <p
                    v-if="!detail.latest_errors.length"
                    class="text-p-sm text-ink-gray-6"
                  >
                    {{ __("No errors in this period.") }}
                  </p>
                  <table v-else class="w-full min-w-[44rem] text-p-sm">
                    <thead>
                      <tr class="text-left text-ink-gray-5">
                        <th scope="col" class="py-1.5 pr-3 font-medium">
                          {{ __("When") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Job") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("Type") }}
                        </th>
                        <th scope="col" class="px-3 py-1.5 font-medium">
                          {{ __("The provider said") }}
                        </th>
                        <th scope="col" class="py-1.5 pl-3 font-medium">
                          {{ __("Fallback") }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, i) in detail.latest_errors"
                        :key="i"
                        class="border-t border-outline-gray-1 align-top"
                      >
                        <td class="whitespace-nowrap py-1.5 pr-3">
                          {{ row.when }}
                        </td>
                        <td class="px-3 py-1.5">{{ row.job || "-" }}</td>
                        <td class="px-3 py-1.5">{{ row.kind }}</td>
                        <td class="px-3 py-1.5 text-ink-gray-6">
                          {{ row.message || "-" }}
                        </td>
                        <td class="py-1.5 pl-3">
                          <Badge
                            :label="
                              row.fallback_answered
                                ? __('Answered')
                                : __('No answer')
                            "
                            :theme="row.fallback_answered ? 'green' : 'gray'"
                            size="sm"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </SectionCard>
            </template>
          </template>
        </template>

        <!-- 3. which model each job uses -->
        <template v-else-if="view === 'settings' && settings">
          <p class="text-p-sm text-ink-gray-6">
            {{
              settings.can_change
                ? __(
                    "Each job has its own first model and its own fallback. Turn the fallback off where a weaker answer is worse than no answer."
                  )
                : __("Only System Managers change these.")
            }}
          </p>
          <p
            v-if="notice"
            role="status"
            class="rounded-lg px-3 py-2 text-p-sm"
            :class="
              notice.ok
                ? 'bg-success-soft text-success'
                : 'bg-warning-soft text-warning'
            "
          >
            {{ notice.text }}
          </p>
          <div class="overflow-x-auto rounded-xl border border-outline-gray-2">
            <table class="w-full min-w-[68rem] text-p-sm">
              <thead>
                <tr class="bg-surface-gray-1 text-left text-ink-gray-5">
                  <th scope="col" class="px-4 py-2.5 font-medium">
                    {{ __("Job") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("Tries first") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("Fallback") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("OpenAI model") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 font-medium">
                    {{ __("Anthropic-compatible model") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Calls") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Errors") }}
                  </th>
                  <th scope="col" class="px-3 py-2.5 text-right font-medium">
                    {{ __("Cost") }}
                  </th>
                  <th scope="col" class="px-4 py-2.5">
                    <span class="sr-only">{{ __("Test") }}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="job in settings.jobs"
                  :key="job.job"
                  class="border-t border-outline-gray-1 align-top"
                >
                  <td class="px-4 py-3">
                    <div class="text-base-medium text-ink-gray-9">
                      {{ job.job }}
                    </div>
                    <div class="text-ink-gray-5">
                      {{ job.primary ? job.primary.model : __("not set up") }}
                      <template v-if="job.fallback">
                        → {{ job.fallback.model }}
                      </template>
                    </div>
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="select"
                      :aria-label="__('First section for {0}', job.job)"
                      :model-value="job.primary_section"
                      :options="sectionOptions"
                      :disabled="!settings.can_change || saving"
                      @update:model-value="
                        save(job.job, { primary_section: $event })
                      "
                    />
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="select"
                      :aria-label="__('Fallback for {0}', job.job)"
                      :model-value="job.allow_fallback"
                      :options="fallbackOptions"
                      :disabled="!settings.can_change || saving"
                      @update:model-value="
                        save(job.job, { allow_fallback: $event })
                      "
                    />
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="text"
                      :aria-label="__('OpenAI model for {0}', job.job)"
                      :model-value="job.openai_model"
                      :placeholder="sectionModel('OpenAI')"
                      :disabled="!settings.can_change || saving"
                      @change="
                        save(job.job, { openai_model: $event.target.value })
                      "
                    />
                  </td>
                  <td class="px-3 py-3">
                    <FormControl
                      type="text"
                      :aria-label="
                        __('Anthropic-compatible model for {0}', job.job)
                      "
                      :model-value="job.anthropic_model"
                      :placeholder="sectionModel('Anthropic-compatible')"
                      :disabled="!settings.can_change || saving"
                      @change="
                        save(job.job, { anthropic_model: $event.target.value })
                      "
                    />
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ job.calls.toLocaleString() }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ pct(job.error_rate) }}
                  </td>
                  <td class="px-3 py-3 text-right tabular-nums">
                    {{ money(job.cost) }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    <Button
                      v-if="settings.can_change"
                      :label="__('Try')"
                      :loading="trying === job.job"
                      :disabled="!!trying"
                      @click="tryJob(job.job)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-p-xs text-ink-gray-5">
            {{
              __(
                "Blank model: the section's own model. Keys and the sections themselves are in Settings → AI providers."
              )
            }}
          </p>

          <SectionCard :title="__('Change history')">
            <ul class="flex flex-col gap-1.5 px-4 pb-4 text-p-sm">
              <li v-for="(c, i) in settings.changes" :key="i">
                <span class="text-ink-gray-5">{{
                  String(c.creation).slice(0, 16)
                }}</span>
                · {{ c.changed_by }} ·
                <span class="text-base-medium text-ink-gray-9">{{
                  c.job
                }}</span>
                {{ c.setting }}: {{ c.old_value }} → {{ c.new_value }}
              </li>
              <li v-if="!settings.changes.length" class="text-ink-gray-5">
                {{ __("No changes yet.") }}
              </li>
            </ul>
          </SectionCard>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import WeekLineChart from "@/pages/sales-dashboard/WeekLineChart.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Badge,
  Button,
  call,
  FormControl,
  TabButtons,
  usePageMeta,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import BarList from "./BarList.vue";

const API = "helpdesk.api.ai_models";
const STATUS_THEME: Record<string, "green" | "orange" | "red" | "gray"> = {
  Healthy: "green",
  Degraded: "orange",
  Paused: "red",
  "Not used": "gray",
};

type Figures = {
  calls: number;
  failed: number;
  error_rate: number | null;
  fallback_rate: number | null;
  cost: number;
  p50: number | null;
  p95: number | null;
};
type UsedFor = { primary: string[]; fallback: string[] };
type ModelRow = Figures & {
  model: string;
  provider: string;
  used_for: UsedFor;
  status: string;
};
type Overview = {
  days: number;
  totals: Figures;
  budget_usd: number;
  models: ModelRow[];
  attention: string[];
  recorded_since: string;
};
type Detail = ModelRow & {
  series: { day: string; calls: number; cost: number; error_rate: number }[];
  by_job: (Figures & { name: string })[];
  errors_by_kind: { kind: string; count: number }[];
  errors_by_job: (Figures & { name: string })[];
  latest_errors: {
    when: string;
    job: string;
    kind: string;
    message: string;
    fallback_answered: boolean;
  }[];
  slowest: { when: string; job: string; ticket: string; seconds: number }[];
};
type Step = { section: string; model: string; ready: boolean };
type JobRow = Figures & {
  job: string;
  primary: Step | null;
  fallback: Step | null;
  primary_section: string;
  allow_fallback: string;
  openai_model: string;
  anthropic_model: string;
};
type Settings = {
  jobs: JobRow[];
  sections: Step[];
  defaults: { primary_section: string; failover: boolean };
  can_change: boolean;
  changes: Record<string, string>[];
};

const route = useRoute();
const router = useRouter();
usePageMeta(() => ({ title: __("AI models") }));

const VIEWS = ["models", "model", "settings"];
const view = computed(() =>
  VIEWS.includes(route.query.view as string)
    ? (route.query.view as string)
    : "models"
);
const days = computed(() =>
  [7, 30, 90].includes(Number(route.query.days)) ? Number(route.query.days) : 30
);
const model = computed(() => (route.query.model as string) || "");
const tab = computed(() =>
  route.query.tab === "errors" ? "errors" : "performance"
);
const views = [
  { label: __("Models"), value: "models" },
  { label: __("One model"), value: "model" },
  { label: __("Model settings"), value: "settings" },
];
const periods = [
  { label: __("7 days"), value: "7" },
  { label: __("30 days"), value: "30" },
  { label: __("90 days"), value: "90" },
];
const tabs = [
  { label: __("Performance"), value: "performance" },
  { label: __("Errors"), value: "errors" },
];

function go(change: Record<string, string>) {
  router.replace({ query: { ...route.query, ...change } });
}

const overview = ref<Overview | null>(null);
const detail = ref<Detail | null>(null);
const settings = ref<Settings | null>(null);
const loading = ref(false);
const error = ref<unknown>(null);
let latest = 0;

// only the newest request fills the page
async function load() {
  const mine = ++latest;
  loading.value = true;
  error.value = null;
  try {
    // the model list (for the picker) comes with every view
    const o = (await call(`${API}.overview`, { days: days.value })) as Overview;
    if (mine !== latest) return;
    overview.value = o;
    if (view.value === "model") {
      const name = model.value || o.models[0]?.model || "";
      if (name && !model.value) return go({ model: name });
      detail.value = name
        ? ((await call(`${API}.detail`, {
            model: name,
            days: days.value,
          })) as Detail)
        : null;
    } else if (view.value === "settings") {
      settings.value = (await call(`${API}.job_settings`, {
        days: days.value,
      })) as Settings;
    }
  } catch (err) {
    if (mine === latest) error.value = err;
  } finally {
    if (mine === latest) loading.value = false;
  }
}
watch([view, days, model], load, { immediate: true });

const shown = computed(() =>
  view.value === "models"
    ? overview.value
    : view.value === "model"
    ? detail.value || !model.value
    : settings.value
);
const usedModels = computed(
  () => (overview.value?.models || []).filter((m) => m.calls).length
);
const modelOptions = computed(() =>
  (overview.value?.models || []).map((m) => ({
    label: m.model,
    value: m.model,
  }))
);

function money(v: number | null | undefined) {
  return `$${(v || 0).toFixed(2)}`;
}
function pct(v: number | null | undefined) {
  return v === null || v === undefined ? "-" : `${v}%`;
}
function seconds(v: number | null | undefined) {
  return v === null || v === undefined ? "-" : `${v} s`;
}
function speed(p50: number | null, p95: number | null) {
  return p50 === null ? "-" : `${p50} s / ${p95} s`;
}
function usedFor(used: UsedFor) {
  const parts = [];
  if (used.primary.length)
    parts.push(__("First for: {0}", used.primary.join(", ")));
  if (used.fallback.length)
    parts.push(__("Fallback for: {0}", used.fallback.join(", ")));
  return parts.join(" · ") || __("No job uses it");
}

function bars<T extends Record<string, any>>(
  rows: T[],
  key: string,
  text: (v: number) => string,
  tone = "",
  name = "model"
) {
  const withValue = rows.filter((r) => r[key]);
  const max = Math.max(0, ...withValue.map((r) => r[key] as number));
  return withValue.map((r) => ({
    label: String(r[name]),
    share: max ? (r[key] / max) * 100 : 0,
    text: text(r[key]),
    tone,
  }));
}

const dayLabels = computed(() =>
  (detail.value?.series || []).map((d) => d.day.slice(5))
);
function line(
  name: string,
  key: "cost" | "calls" | "error_rate",
  color = "--brand"
) {
  return {
    name,
    color,
    values: (detail.value?.series || []).map((d) => d[key] || 0),
  };
}

// --- model settings ---------------------------------------------------------------------------

const saving = ref(false);
const trying = ref("");
const notice = ref<{ ok: boolean; text: string } | null>(null);
const sectionOptions = computed(() => [
  {
    label: __("Default ({0})", settings.value?.defaults.primary_section || ""),
    value: "",
  },
  { label: "OpenAI", value: "OpenAI" },
  { label: "Anthropic-compatible", value: "Anthropic-compatible" },
]);
const fallbackOptions = computed(() => [
  {
    label: __(
      "Default ({0})",
      settings.value?.defaults.failover ? __("On") : __("Off")
    ),
    value: "",
  },
  { label: __("On"), value: "On" },
  { label: __("Off"), value: "Off" },
]);
function sectionModel(section: string) {
  return (
    settings.value?.sections.find((s) => s.section === section)?.model || ""
  );
}

async function save(job: string, values: Record<string, string>) {
  saving.value = true;
  notice.value = null;
  try {
    await call(`${API}.save_job`, { job, values: JSON.stringify(values) });
    notice.value = { ok: true, text: __("Saved: {0}", job) };
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not saved")) };
  } finally {
    saving.value = false;
    load();
  }
}

async function tryJob(job: string) {
  trying.value = job;
  notice.value = null;
  try {
    const r = (await call(`${API}.try_job`, { job })) as {
      ok: boolean;
      message: string;
    };
    notice.value = { ok: r.ok, text: `${job}: ${r.message}` };
  } catch (err) {
    notice.value = {
      ok: false,
      text: errorText(err, __("The test call failed")),
    };
  } finally {
    trying.value = "";
  }
}
</script>
