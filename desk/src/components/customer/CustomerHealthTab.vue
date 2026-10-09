<template>
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-lg-semibold text-ink-gray-9">{{ __("Health") }}</h2>
      <Button
        variant="ghost"
        :label="__('Refresh')"
        :loading="loading"
        @click="emit('retry')"
      >
        <template #prefix>
          <LucideRefreshCw class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <div
      v-if="loading && !health"
      class="flex flex-col gap-3"
      :aria-label="__('Loading')"
    >
      <span class="h-16 animate-pulse rounded-lg bg-surface-gray-2" />
      <span class="h-64 animate-pulse rounded-lg bg-surface-gray-2" />
    </div>

    <TaskyState
      v-else-if="error && !health"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t work out this customer\'s health')"
      :message="errorText(error, __('Check your connection and try again.'))"
      error
    >
      <Button :label="__('Retry')" @click="emit('retry')" />
    </TaskyState>

    <TaskyState
      v-else-if="!health"
      :icon="LucideCircleDashed"
      :title="__('No health yet')"
      :message="
        __(
          'This customer is new. Its health is worked out within a few minutes; refresh to see it.'
        )
      "
    >
      <Button :label="__('Refresh')" @click="emit('retry')" />
    </TaskyState>

    <template v-else>
      <div
        class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-base p-4 sm:flex-row sm:items-center sm:gap-4"
      >
        <TaskyBadge v-bind="healthBadge(health.status)" class="self-start" />
        <p class="min-w-0 text-p-sm text-ink-gray-7">{{ summary }}</p>
      </div>

      <ul
        role="list"
        class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
      >
        <li
          v-for="signal in ordered"
          :key="signal.key"
          class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 sm:flex-row sm:items-start sm:gap-4"
        >
          <component
            :is="signalLook(signal.state).icon"
            class="mt-0.5 hidden size-4 shrink-0 sm:block"
            :class="iconClass(signal)"
            aria-hidden="true"
          />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <h3 class="text-base-medium text-ink-gray-9">
                {{ signal.label }}
              </h3>
              <span
                class="inline-flex items-center gap-1 text-xs font-medium"
                :class="INK[signalLook(signal.state).tone]"
              >
                <component
                  :is="signalLook(signal.state).icon"
                  class="size-3.5 sm:hidden"
                  aria-hidden="true"
                />
                {{ signalStateLabel(signal.state) }}
              </span>
              <span
                v-if="signal.points"
                class="font-mono text-xs tabular-nums text-ink-gray-5"
              >
                {{ pointsLabel(signal.points) }}
              </span>
            </div>
            <p
              class="mt-0.5 text-p-sm"
              :class="
                signal.state === 'skipped'
                  ? 'text-ink-gray-5'
                  : 'text-ink-gray-8'
              "
            >
              {{ signal.value }}
            </p>
            <p class="mt-1 text-p-xs text-ink-gray-5">
              {{ signal.rule }}
              {{ weightLabel(signal.weight) }}
            </p>
          </div>
          <RouterLink
            v-if="signal.link"
            :to="route(signal).to"
            class="shrink-0 self-start rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :aria-label="__('{0}: open {1}', signal.label, route(signal).label)"
          >
            {{ route(signal).label }}
          </RouterLink>
        </li>
      </ul>

      <p class="text-p-xs text-ink-gray-5">
        {{
          __(
            "A signal on watch counts its weight, one at risk twice its weight. {0} points or more is Watch, {1} or more At risk. Signals without data don't count. Refreshed every 10 minutes.",
            String(health.thresholds.watch),
            String(health.thresholds.at_risk)
          )
        }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { INK } from "@/components/tone";
import {
  healthBadge,
  signalLook,
  signalRoute,
  signalStateLabel,
  type CustomerHealth,
  type HealthSignal,
} from "@/composables/customerHealth";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import { computed } from "vue";
import { RouterLink } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideRefreshCw from "~icons/lucide/refresh-cw";

const props = defineProps<{
  customer: string;
  health: CustomerHealth | null;
  loading: boolean;
  error?: unknown;
}>();
const emit = defineEmits<{ retry: [] }>();

const auth = useAuthStore();

const STATE_ORDER = { at_risk: 0, watch: 1, ok: 2, skipped: 3 };

/** What counts against the customer first, then what's fine, then what has no data. */
const ordered = computed(() =>
  [...(props.health?.signals ?? [])].sort(
    (a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state] || b.points - a.points
  )
);

const summary = computed(() => {
  const health = props.health;
  if (!health) return "";
  if (health.status === "no_data")
    return __(
      "Nothing to judge yet: no recent tickets, open work, contract, sign-off or ERP connection."
    );
  if (!health.reasons.length) return __("Every signal with data is fine.");
  return __(
    "{0} points from: {1}.",
    String(health.points),
    health.reasons.join(", ")
  );
});

function iconClass(signal: HealthSignal) {
  return signal.state === "ok" || signal.state === "skipped"
    ? "text-ink-gray-4"
    : INK[signalLook(signal.state).tone];
}

function pointsLabel(points: number) {
  return points === 1 ? __("1 point") : __("{0} points", String(points));
}

function weightLabel(weight: number) {
  return __("Weight {0}.", String(weight));
}

function route(signal: HealthSignal) {
  return signalRoute(signal.link!, props.customer, auth.canSeeOverview);
}
</script>
