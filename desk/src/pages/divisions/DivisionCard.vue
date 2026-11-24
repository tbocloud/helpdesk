<template>
  <RouterLink
    :to="{
      name: 'DivisionDashboard',
      params: { division: card.name },
      query: periodQuery,
    }"
    class="group flex flex-col rounded-xl border border-outline-gray-2 bg-surface-base transition-colors hover:border-outline-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
    :aria-label="__('Open the {0} division\'s dashboard', card.division_name)"
  >
    <header class="flex items-start gap-3 px-5 pb-3 pt-4">
      <div class="min-w-0 flex-1">
        <h2 class="truncate text-lg font-semibold text-ink-gray-9">
          {{ card.division_name }}
        </h2>
        <p class="truncate text-p-sm text-ink-gray-6">
          {{ [card.country, card.currency].filter(Boolean).join(" · ") }}
        </p>
      </div>
      <span
        class="rounded-md bg-surface-gray-2 px-2 py-0.5 font-mono text-xs text-ink-gray-7"
      >
        {{ card.name }}
      </span>
    </header>

    <dl class="grid grid-cols-3 gap-px border-y border-outline-gray-1 bg-surface-gray-1">
      <div v-for="figure in figures" :key="figure.label" class="bg-surface-base px-4 py-3">
        <dt class="text-xs text-ink-gray-6">{{ figure.label }}</dt>
        <dd
          class="mt-0.5 font-mono text-lg font-semibold tabular-nums"
          :class="figure.danger ? 'text-danger' : 'text-ink-gray-9'"
        >
          {{ figure.value }}
        </dd>
      </div>
    </dl>

    <ul class="flex flex-1 flex-col gap-2 px-5 py-4 text-p-sm text-ink-gray-7">
      <li class="flex items-center gap-2">
        <LucideShieldUser class="size-4 shrink-0 text-ink-gray-6" aria-hidden="true" />
        <span class="truncate">
          {{
            card.admins.length
              ? __("Run by {0}", card.admins.join(", "))
              : __("No Division Admin yet")
          }}
        </span>
      </li>
      <li class="flex items-center gap-2">
        <LucideUsers class="size-4 shrink-0 text-ink-gray-6" aria-hidden="true" />
        <span>{{ peopleText }}</span>
      </li>
      <li class="flex items-center gap-2">
        <component
          :is="health.tone ? LucideTriangleAlert : LucideDatabase"
          class="size-4 shrink-0"
          :class="health.tone ? TONE_INK[health.tone] : 'text-ink-gray-6'"
          aria-hidden="true"
        />
        <span
          class="truncate"
          :class="health.tone ? TONE_INK[health.tone] : ''"
        >
          {{ health.label }}
        </span>
      </li>
    </ul>

    <footer
      class="flex items-center justify-between border-t border-outline-gray-1 px-5 py-3 text-sm font-medium text-brand-ink"
    >
      {{ __("Open dashboard") }}
      <LucideArrowRight
        class="size-4 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
        aria-hidden="true"
      />
    </footer>
  </RouterLink>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideDatabase from "~icons/lucide/database";
import LucideShieldUser from "~icons/lucide/shield-user";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import { formatValue } from "./chartLook";
import { siteHealth, type DivisionCard } from "./divisions";

const props = defineProps<{ card: DivisionCard }>();

const route = useRoute();
// the dashboard opens on the same period
const periodQuery = computed(() => {
  const { period, from, to } = route.query;
  return Object.fromEntries(
    Object.entries({ period, from, to }).filter(([, v]) => v)
  );
});

const count = (v: number | null) => formatValue("count", v, null);
const figures = computed(() => [
  { label: __("Leads"), value: count(props.card.leads) },
  {
    label: __("Conversion"),
    value: formatValue("percent", props.card.conversion_rate, null),
  },
  { label: __("Open projects"), value: count(props.card.active_projects) },
  { label: __("Open leads"), value: count(props.card.open_leads) },
  { label: __("Pending tasks"), value: count(props.card.pending_tasks) },
  {
    label: __("Overdue"),
    value: count(props.card.overdue_tasks),
    danger: props.card.overdue_tasks > 0,
  },
]);

const peopleText = computed(() =>
  props.card.people === 1
    ? __("1 person")
    : __("{0} people", count(props.card.people))
);
const health = computed(() => siteHealth(props.card.site));
// full class names, so Tailwind finds them
const TONE_INK = { danger: "text-danger", warning: "text-warning" };
</script>
