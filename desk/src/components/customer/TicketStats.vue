<template>
  <!-- ticket figures for one customer or contact, over a chosen period -->
  <section class="px-5 pb-4" :aria-labelledby="headingId">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 :id="headingId" class="text-base-medium text-ink-gray-9">
        {{ __("Support figures") }}
      </h2>
      <FormControl
        v-model="period"
        type="select"
        class="w-36"
        :options="PERIODS"
        :aria-label="__('Period for the figures')"
      />
    </div>

    <div
      v-if="stats.error && !stats.data"
      class="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-outline-gray-2 px-4 py-3 text-p-sm text-ink-gray-6"
      role="alert"
    >
      {{ errorText(stats.error, __("Couldn't load the ticket figures.")) }}
      <Button size="sm" :label="__('Retry')" @click="stats.reload()" />
    </div>

    <div v-else class="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatTile
        compact
        :label="__('Avg. first response')"
        :value="duration(data?.avg_first_response_time)"
        :sub="change(data?.avg_first_response_time)"
        :icon="LucideReply"
        :loading="loading"
      />
      <StatTile
        compact
        :label="__('Avg. resolution')"
        :value="duration(data?.avg_resolution_time)"
        :sub="change(data?.avg_resolution_time)"
        :icon="LucideCircleCheckBig"
        :loading="loading"
      />
      <StatTile
        compact
        :label="__('SLAs failed')"
        :value="data?.sla_violations.total ?? '–'"
        :sub="change(data?.sla_violations)"
        :icon="LucideAlarmClockOff"
        :icon-tone="data?.sla_violations.total ? 'danger' : 'neutral'"
        :value-tone="data?.sla_violations.total ? 'danger' : 'neutral'"
        :loading="loading"
      />
      <StatTile
        compact
        :label="__('Rating')"
        :value="rating"
        :sub="ratingSub"
        :icon="LucideStar"
        :loading="loading"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import { __ } from "@/translation";
import { errorText, formatTime } from "@/utils";
import { Button, createResource, FormControl } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideAlarmClockOff from "~icons/lucide/alarm-clock-off";
import LucideCircleCheckBig from "~icons/lucide/circle-check-big";
import LucideReply from "~icons/lucide/reply";
import LucideStar from "~icons/lucide/star";

interface Metric {
  /** null: nothing in the previous period to compare with */
  percentage_change: number | null;
  average?: number;
  total?: number;
}

interface Stats {
  feedback_received: { average: number; total: number };
  sla_violations: Metric & { total: number };
  avg_first_response_time: Metric & { average: number };
  avg_resolution_time: Metric & { average: number };
}

const props = defineProps<{
  dt: "HD Customer" | "Contact";
  dn: string;
}>();

// values are helpdesk.api.ticket_stats' period keys, which count days back from today
const PERIODS = [
  { value: "last week", label: __("Last 7 days"), days: 7 },
  { value: "last month", label: __("Last 30 days"), days: 30 },
  { value: "last 3 months", label: __("Last 90 days"), days: 90 },
];

const headingId = `ticket-stats-${useId()}`;
const period = ref("last month");

const stats = createResource({
  url: "helpdesk.api.ticket_stats.get_ticket_stats",
  method: "GET",
  makeParams: () => ({ dt: props.dt, dn: props.dn, period: period.value }),
  auto: true,
});
watch(period, () => stats.reload());

const data = computed<Stats | null>(() => stats.data ?? null);
const loading = computed(() => stats.loading && !stats.data);
const days = computed(
  () => PERIODS.find((p) => p.value === period.value)?.days ?? 30
);

function duration(metric?: Metric) {
  if (!metric?.average) return "–";
  return (
    formatTime(metric.average, {
      day: true,
      hour: true,
      minute: true,
      maxUnits: 2,
    }) || __("Under 1m")
  );
}

/** How this period compares with the one before it, in words; no colour. */
function change(metric?: Metric) {
  if (!metric) return undefined;
  const pc = metric.percentage_change;
  if (pc === null) return __("None in the {0} days before", String(days.value));
  if (pc === 0) return __("Same as the {0} days before", String(days.value));
  const value = `${pc > 0 ? "+" : ""}${Math.round(pc)}%`;
  return __("{0} on the {1} days before", value, String(days.value));
}

const rating = computed(() => {
  const feedback = data.value?.feedback_received;
  return feedback?.total ? `${feedback.average}/5` : "–";
});

const ratingSub = computed(() => {
  const total = data.value?.feedback_received.total ?? 0;
  if (!total) return __("No ratings yet");
  return total === 1
    ? __("1 rating, all time")
    : __("{0} ratings, all time", String(total));
});
</script>
