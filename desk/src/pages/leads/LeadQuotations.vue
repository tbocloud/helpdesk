<template>
  <!-- read only; a proposal prices the lead through these (docs/proposals.md) -->
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Quotations')"
  >
    <h2
      class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
    >
      {{ __("Quotations") }}
    </h2>
    <p v-if="!quotations.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
      {{ __("No quotations for this lead on the ERP site yet.") }}
    </p>
    <ul v-else role="list">
      <li
        v-for="q in quotations"
        :key="q.name"
        class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <span class="truncate font-mono text-sm text-ink-gray-8">{{
            q.name
          }}</span>
          <span
            v-if="q.transaction_date"
            class="text-xs tabular-nums text-ink-gray-6"
          >
            {{ dayjs(q.transaction_date).format("D MMM YYYY") }}
          </span>
        </div>
        <TaskyBadge v-if="q.tbo_quote_status" :label="q.tbo_quote_status" />
        <span
          v-if="q.grand_total !== undefined && q.grand_total !== null"
          class="font-mono text-sm tabular-nums text-ink-gray-9"
        >
          {{ q.currency ? money(q.grand_total, q.currency) : q.grand_total }}
        </span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { LeadQuotation } from "./leads";

defineProps<{ quotations: LeadQuotation[] }>();
</script>
