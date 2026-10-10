<template>
  <ul v-if="rows.length" role="list">
    <li
      v-for="row in rows"
      :key="`${row.doctype}:${row.name}`"
      class="flex items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
    >
      <component
        :is="row.doctype === 'HD Ticket' ? LucideTicket : LucideSquareCheck"
        class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
        aria-hidden="true"
      />
      <div class="min-w-0 flex-1">
        <RouterLink
          :to="row.link"
          class="block truncate rounded text-base text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ row.title }}
        </RouterLink>
        <p
          class="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-ink-gray-5"
        >
          <EscalationBadge :level="row.level" />
          <span v-if="row.days" class="font-mono text-xs tabular-nums">
            {{ __("{0} working days late", String(row.days)) }}
          </span>
          <span v-if="owners(row)" class="truncate">· {{ owners(row) }}</span>
        </p>
      </div>
    </li>
  </ul>
  <p v-else class="flex items-center gap-2 px-4 py-6 text-p-sm text-ink-gray-6">
    <LucideCircleCheck class="size-4 text-success" aria-hidden="true" />
    {{ empty }}
  </p>
</template>

<script setup lang="ts">
import EscalationBadge from "@/components/EscalationBadge.vue";
import type { FollowUpRow } from "@/components/followUps";
import { __ } from "@/translation";
import { RouterLink } from "vue-router";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTicket from "~icons/lucide/ticket";

defineProps<{ rows: FollowUpRow[]; empty: string }>();

function owners(row: FollowUpRow) {
  return row.owners.map((o) => o.full_name).join(", ");
}
</script>
