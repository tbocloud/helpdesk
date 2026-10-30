<template>
  <!-- for managers and heads: out quietly for anyone else, an older ERP site or no batches -->
  <section
    v-if="people.length"
    :aria-labelledby="headingId"
    class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-busy="report.loading"
  >
    <div class="flex items-baseline justify-between gap-3 px-4 pt-4">
      <h2 :id="headingId" class="text-base-medium text-ink-gray-9">
        {{ __("Call batches") }}
      </h2>
      <p class="font-mono text-p-xs tabular-nums text-ink-gray-6">
        {{
          __(
            "{0} / {1} called",
            String(totals.called ?? 0),
            String(totals.size ?? 0)
          )
        }}
      </p>
    </div>
    <div
      class="grid-row hidden border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-6 md:grid"
      aria-hidden="true"
    >
      <span>{{ __("Salesperson") }}</span>
      <span>{{ __("Batches") }}</span>
      <span class="text-right">{{ __("Called") }}</span>
      <span class="text-right">{{ __("Connected") }}</span>
      <span class="text-right">{{ __("Overdue") }}</span>
    </div>
    <ul role="list" class="divide-y divide-outline-gray-1">
      <li
        v-for="p in people"
        :key="`${p.user}-${p.department}`"
        class="grid-row px-4 py-3"
      >
        <span
          class="col-span-3 truncate text-sm-medium text-ink-gray-9 md:col-span-1"
          >{{ p.user_name }}</span
        >
        <span class="col-span-3 text-p-sm text-ink-gray-7 md:col-span-1">{{
          batchText(p)
        }}</span>
        <span class="cell">
          <span class="cell-label">{{ __("Called") }}</span>
          <span class="font-mono text-sm tabular-nums text-ink-gray-9"
            >{{ p.called }} / {{ p.size }}</span
          >
        </span>
        <span class="cell">
          <span class="cell-label">{{ __("Connected") }}</span>
          <span class="font-mono text-sm tabular-nums text-ink-gray-9">{{
            p.connected
          }}</span>
        </span>
        <span class="cell">
          <span class="cell-label">{{ __("Overdue") }}</span>
          <span
            class="inline-flex items-center gap-1 font-mono text-sm tabular-nums"
            :class="p.overdue ? 'font-medium text-danger' : 'text-ink-gray-9'"
          >
            <LucideAlarmClock
              v-if="p.overdue"
              class="size-3.5"
              aria-hidden="true"
            />
            {{ p.overdue }}
          </span>
        </span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { createResource } from "frappe-ui";
import { computed, useId, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import type { BatchReport, BatchReportPerson } from "./callBatches";

const props = defineProps<{ date: string }>();
const headingId = `call-batches-${useId()}`;

const report = createResource({
  url: "helpdesk.api.call_batches.get_call_batches_report",
  makeParams: () => ({ date: props.date }),
  auto: true,
  // someone who may not open it, or an older ERP site: the table just stays out
  onError() {},
});
watch(
  () => props.date,
  () => report.reload()
);
defineExpose({ reload: () => report.reload() });

const data = computed(() => report.data as BatchReport | undefined);
const people = computed(() => (data.value?.available ? data.value.people : []));
const totals = computed(() => data.value?.totals ?? {});

function batchText(p: BatchReportPerson) {
  return p.batches.map((b) => `${b.slot} ${b.called}/${b.size}`).join(" · ");
}
</script>

<style scoped>
.grid-row {
  @apply grid grid-cols-3 gap-x-3 gap-y-1;
}
.cell {
  @apply flex flex-col md:items-end;
}
.cell-label {
  @apply text-2xs text-ink-gray-6 md:hidden;
}
@media (min-width: 768px) {
  .grid-row {
    @apply items-center;
    grid-template-columns:
      minmax(0, 1.5fr) minmax(0, 2fr)
      repeat(3, minmax(4.5rem, 1fr));
  }
}
</style>
