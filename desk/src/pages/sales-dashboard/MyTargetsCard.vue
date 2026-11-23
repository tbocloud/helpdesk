<template>
  <!-- this month's targets, counted from the person's leads as the Sales targets page counts them -->
  <section
    class="flex min-w-0 flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :aria-labelledby="heading"
  >
    <header class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-0.5">
        <h2 :id="heading" class="text-base font-semibold text-ink-gray-9">
          {{ __("{0} targets", monthTitle(month)) }}
        </h2>
        <p v-if="target" class="text-xs tabular-nums text-ink-gray-6">
          {{
            __(
              "Set by {0} · {1} days left in the month",
              target.assigned_by_name || target.assigned_by,
              String(daysLeft)
            )
          }}
        </p>
      </div>
      <RouterLink
        :to="{ name: 'MyTargets' }"
        class="inline-flex shrink-0 items-center gap-1 rounded text-sm font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      >
        {{ __("All targets") }}
        <LucideArrowRight class="size-3.5" aria-hidden="true" />
      </RouterLink>
    </header>

    <div
      v-if="mine.loading || progress.loading"
      class="h-40 animate-pulse rounded-lg bg-surface-gray-3"
      aria-busy="true"
      :aria-label="__('Loading')"
    />
    <p
      v-else-if="mine.error || progress.data?.state === 'unavailable'"
      class="py-6 text-center text-sm text-ink-gray-6"
    >
      {{
        progress.data?.reason ||
        errorText(mine.error, __("Couldn't count your targets."))
      }}
    </p>
    <p
      v-else-if="!figures.length"
      class="py-6 text-center text-sm text-ink-gray-6"
    >
      {{ __("No targets for this month yet.") }}
    </p>
    <ul v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <li
        v-for="figure in figures"
        :key="figure.criterion.criterion"
        class="flex min-w-0 items-center gap-3 rounded-lg border border-outline-gray-2 p-3"
      >
        <TargetRing
          :actual="Math.round(figure.result.percent ?? 0)"
          :target="100"
          :tone="RING_TONE[figure.result.standing]"
          :status-text="figure.result.standingText"
          :text="`${Math.round(figure.result.percent ?? 0)}%`"
        />
        <div class="flex min-w-0 flex-col gap-0.5">
          <span class="flex flex-wrap items-center gap-1.5">
            <span class="truncate text-sm font-semibold text-ink-gray-9">
              {{ figure.criterion.criterion }}
            </span>
            <span
              class="rounded-full px-2 py-0.5 text-2xs font-medium"
              :class="TONE_CLASSES[RING_TONE[figure.result.standing]]"
              >{{ figure.result.standingText }}</span
            >
          </span>
          <span class="text-lg font-bold tabular-nums text-ink-gray-9">
            {{ figure.achieved }}
            <span class="text-xs font-normal text-ink-gray-6">
              {{ __("of {0}", figure.target) }}
            </span>
          </span>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { TONE_CLASSES, type Tone } from "@/components/tone";
import TargetRing from "@/pages/leads/TargetRing.vue";
import {
  figureText,
  monthTitle,
  monthValue,
  progressOf,
  targetText,
  type MyTargets,
  type Progress,
  type Standing,
} from "@/pages/sales-targets/salesTargets";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { createResource, dayjs } from "frappe-ui";
import { computed, useId, watch } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";

const heading = useId();
const month = monthValue();
const daysLeft = dayjs().daysInMonth() - dayjs().date();

const mine = createResource<MyTargets>({
  url: "helpdesk.api.sales_targets.get_my_targets",
  params: { month },
  auto: true,
});
const progress = createResource<Progress>({
  url: "helpdesk.api.sales_targets.get_progress",
  params: { month },
});
const target = computed(() => mine.data?.target ?? null);
watch(
  () => target.value?.modified,
  (modified) => modified && progress.reload(),
  { immediate: true }
);

// a target behind pace is warning, never danger: not reached yet isn't a failure (ui-guidelines §8)
const RING_TONE: Record<Standing, Tone> = {
  done: "success",
  on_pace: "success",
  behind: "warning",
  short: "warning",
  below: "warning",
  none: "neutral",
};

// the counted targets; written KPIs stay on the Sales targets page
const figures = computed(() => {
  const counted = progress.data;
  if (!target.value || counted?.state !== "counted") return [];
  const currency = mine.data!.currency;
  return target.value.criteria
    .filter((c) => c.measure && counted.criteria?.[c.criterion])
    .map((criterion) => {
      const result = progressOf(
        criterion,
        counted.criteria![criterion.criterion],
        counted,
        currency
      );
      return {
        criterion,
        result,
        achieved: figureText(criterion, result.achieved ?? 0, currency),
        target: targetText(criterion, currency),
      };
    });
});

defineExpose({ reload: () => mine.reload() });
</script>
