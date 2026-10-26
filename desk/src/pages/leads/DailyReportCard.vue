<template>
  <article class="flex flex-col gap-4" :aria-labelledby="ids.title">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <h2 :id="ids.title" class="text-lg-medium text-ink-gray-9">
        {{
          __(
            "Daily sales performance · {0} · {1}",
            dayjs(date).format("D MMM YYYY"),
            person.full_name
          )
        }}
      </h2>
      <Button
        :label="__('Copy for WhatsApp')"
        @click="emit('copy', person.text)"
      >
        <template #prefix>
          <LucideCopy class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </header>

    <!-- calls: info; positive leads inside it: success; quotations: warning -->
    <section
      class="section border-outline-gray-2 border-l-info"
      :aria-labelledby="ids.calls"
    >
      <header class="section-head bg-info-soft">
        <LucidePhone class="size-4 text-info" aria-hidden="true" />
        <h3 :id="ids.calls" class="text-base-medium text-ink-gray-9">
          {{ __("Daily call performance") }}
        </h3>
      </header>
      <div class="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
        <div class="figure">
          <span class="figure-value">{{ person.calls_total }}</span>
          <span class="figure-label">{{ __("Total calls made") }}</span>
          <span class="text-xs text-ink-gray-6">{{
            __("{0} connected", String(person.calls_connected))
          }}</span>
        </div>
        <div class="figure">
          <span class="figure-value">{{ person.fresh_leads }}</span>
          <span class="figure-label">{{ __("Fresh leads") }}</span>
        </div>
        <div class="figure">
          <span class="figure-value">{{ person.follow_up_leads }}</span>
          <span class="figure-label">{{ __("Follow-up leads") }}</span>
        </div>
      </div>
      <div class="grid grid-cols-1 gap-3 px-4 pb-4 md:grid-cols-2">
        <div class="sub border-l-success bg-success-soft">
          <div class="flex items-center gap-2">
            <LucideThumbsUp class="size-4 text-success" aria-hidden="true" />
            <h4 class="text-sm-medium text-ink-gray-9">
              {{ __("Positive leads") }}
            </h4>
            <span
              class="ml-auto font-mono text-xl font-semibold tabular-nums text-success"
              >{{ person.positive_leads.length }}</span
            >
          </div>
          <ul v-if="person.positive_leads.length" role="list" class="links">
            <li v-for="lead in person.positive_leads" :key="lead.name">
              <router-link :to="leadRoute(lead.name)" class="link">{{
                leadTitle(lead)
              }}</router-link>
            </li>
          </ul>
          <p v-else class="text-p-xs text-ink-gray-6">
            {{ __("None today.") }}
          </p>
        </div>
        <div class="sub border-l-warning bg-warning-soft">
          <div class="flex items-center gap-2">
            <LucideFileText class="size-4 text-warning" aria-hidden="true" />
            <h4 class="text-sm-medium text-ink-gray-9">
              {{ __("New quotations") }}
            </h4>
            <span
              class="ml-auto font-mono text-xl font-semibold tabular-nums text-warning"
              >{{ person.new_quotations.count }}</span
            >
          </div>
          <p class="font-mono text-sm tabular-nums text-ink-gray-8">
            {{ money(person.new_quotations.value, currency, true) }}
          </p>
          <ul
            v-if="person.new_quotations.items.length"
            role="list"
            class="links"
          >
            <li v-for="item in person.new_quotations.items" :key="item.name">
              <router-link :to="leadRoute(item.lead)" class="link">
                {{ item.lead_name || item.lead }}
                <span class="font-mono tabular-nums text-ink-gray-6">{{
                  money(item.value, currency, true)
                }}</span>
              </router-link>
            </li>
          </ul>
          <p v-else class="text-p-xs text-ink-gray-6">
            {{ __("None today.") }}
          </p>
        </div>
      </div>
    </section>

    <!-- new leads: brand -->
    <section
      class="section border-outline-gray-2 border-l-brand"
      :aria-labelledby="ids.leads"
    >
      <header class="section-head bg-brand-soft">
        <LucideTarget class="size-4 text-brand-ink" aria-hidden="true" />
        <h3 :id="ids.leads" class="text-base-medium text-ink-gray-9">
          {{ __("New leads generated") }}
        </h3>
      </header>
      <div class="flex flex-col gap-3 p-4">
        <div class="figure">
          <span class="figure-value">{{ person.new_leads.length }}</span>
          <span class="figure-label">{{ __("Total new leads") }}</span>
        </div>
        <ol
          v-if="person.new_leads.length"
          class="flex list-decimal flex-col gap-1 pl-6 text-sm marker:font-mono marker:text-ink-gray-6"
        >
          <li v-for="lead in person.new_leads" :key="lead.name">
            <router-link :to="leadRoute(lead.name)" class="link">{{
              leadTitle(lead)
            }}</router-link>
          </li>
        </ol>
        <p v-else class="text-p-sm text-ink-gray-6">
          {{ __("No new leads today.") }}
        </p>
      </div>
    </section>

    <!-- the week against the targets: success when at pace, warning when behind -->
    <section
      class="section border-outline-gray-2 border-l-outline-gray-5"
      :aria-labelledby="ids.week"
    >
      <header class="section-head bg-surface-gray-1">
        <LucideChartNoAxesColumn
          class="size-4 text-ink-gray-7"
          aria-hidden="true"
        />
        <h3 :id="ids.week" class="text-base-medium text-ink-gray-9">
          {{ __("This week vs target") }}
        </h3>
        <span v-if="days" class="ml-auto text-xs text-ink-gray-6">{{
          __("Day {0} of {1}", String(days.elapsed), String(days.total))
        }}</span>
      </header>
      <ul
        v-if="rings.length"
        role="list"
        class="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <li
          v-for="ring in rings"
          :key="ring.metric"
          class="flex items-center gap-3"
        >
          <TargetRing
            :actual="ring.actual"
            :target="ring.target"
            :tone="ring.tone"
            :status-text="ring.status"
          />
          <div class="flex min-w-0 flex-col">
            <span class="text-sm-medium text-ink-gray-9">{{ ring.label }}</span>
            <span class="font-mono text-xs tabular-nums text-ink-gray-6">{{
              __("{0} of {1}", String(ring.actual), String(ring.target))
            }}</span>
            <span
              class="inline-flex items-center gap-1 text-xs"
              :class="INK[ring.tone]"
            >
              <component
                :is="ring.icon"
                class="size-3.5 shrink-0"
                aria-hidden="true"
              />
              {{ ring.status }}
            </span>
          </div>
        </li>
      </ul>
      <p v-else class="p-4 text-p-sm text-ink-gray-6">
        {{
          __(
            "No weekly targets are set. Ask an admin to set them in Settings → CRM."
          )
        }}
      </p>
    </section>
  </article>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import { INK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { Button, dayjs } from "frappe-ui";
import { computed, useId, type Component } from "vue";
import LucideChartNoAxesColumn from "~icons/lucide/chart-no-axes-column";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideCopy from "~icons/lucide/copy";
import LucideFileText from "~icons/lucide/file-text";
import LucidePhone from "~icons/lucide/phone";
import LucideTarget from "~icons/lucide/target";
import LucideThumbsUp from "~icons/lucide/thumbs-up";
import TargetRing from "./TargetRing.vue";
import { leadTitle, type DailyMetric, type DailyPerson } from "./leads";

const props = defineProps<{
  person: DailyPerson;
  date: string;
  currency: string;
  days?: { elapsed: number; total: number };
}>();
const emit = defineEmits<{ (e: "copy", text: string): void }>();

const ids = {
  title: useId(),
  calls: useId(),
  leads: useId(),
  week: useId(),
};

const METRICS: { metric: DailyMetric; label: string; unit: string }[] = [
  { metric: "leads", label: __("New leads"), unit: __("leads") },
  { metric: "meetings", label: __("Meetings"), unit: __("meetings") },
  { metric: "proposals", label: __("Proposals"), unit: __("proposals") },
  { metric: "follow_ups", label: __("Follow-ups"), unit: __("follow-ups") },
];

interface Ring {
  metric: DailyMetric;
  label: string;
  actual: number;
  target: number;
  tone: Tone;
  status: string;
  icon: Component;
}

const rings = computed<Ring[]>(() =>
  METRICS.flatMap(({ metric, label, unit }) => {
    const pace = props.person.pace[metric];
    if (!pace) return [];
    const met = pace.actual >= pace.target;
    const behind = pace.behind > 0;
    return [
      {
        metric,
        label,
        actual: pace.actual,
        target: pace.target,
        tone: behind ? "warning" : "success",
        status: behind
          ? __("Behind by {0} {1}", String(pace.behind), unit)
          : met
            ? __("Target met")
            : __("On track"),
        icon: behind ? LucideClock : LucideCircleCheck,
      } satisfies Ring,
    ];
  })
);

function leadRoute(name: string) {
  return { name: "Lead", params: { leadId: name } };
}
</script>

<style scoped>
.section {
  @apply overflow-hidden rounded-xl border border-l-4 bg-surface-base;
}
.section-head {
  @apply flex items-center gap-2 px-4 py-2.5;
}
.figure {
  @apply flex min-w-0 flex-col;
}
.figure-value {
  @apply font-mono text-3xl font-semibold tabular-nums text-ink-gray-9;
}
.figure-label {
  @apply text-sm text-ink-gray-7;
}
.sub {
  @apply flex flex-col gap-1.5 rounded-lg border-l-4 px-3 py-2.5;
}
.links {
  @apply flex flex-col gap-0.5 text-sm;
}
.link {
  @apply inline-flex min-h-[28px] items-center gap-2 rounded text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight;
}
</style>
