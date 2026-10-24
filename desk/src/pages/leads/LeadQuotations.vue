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
          <!-- staff only: the internal ERPNext Quotation, opened on the ERP site's desk -->
          <a
            v-if="q.url"
            :href="q.url"
            target="_blank"
            rel="noopener"
            class="inline-flex min-w-0 items-center gap-1 self-start rounded font-mono text-sm text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :aria-label="__('Open quotation {0} on the ERP site', q.name)"
          >
            <span class="truncate">{{ q.name }}</span>
            <LucideExternalLink
              class="size-3 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
          </a>
          <span v-else class="truncate font-mono text-sm text-ink-gray-8">{{
            q.name
          }}</span>
          <span class="text-xs tabular-nums text-ink-gray-6">
            <template v-if="q.transaction_date">{{
              dayjs(q.transaction_date).format("D MMM YYYY")
            }}</template>
            <template v-if="q.transaction_date && q.tbo_proposal"> · </template>
            <span v-if="q.tbo_proposal" class="font-mono">{{
              __("for {0}", q.tbo_proposal)
            }}</span>
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
import LucideExternalLink from "~icons/lucide/external-link";
import type { LeadQuotation } from "./leads";

defineProps<{ quotations: LeadQuotation[] }>();
</script>
