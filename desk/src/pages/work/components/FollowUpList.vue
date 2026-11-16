<template>
  <ul v-if="rows.length" role="list">
    <li
      v-for="row in rows"
      :key="`${row.doctype}:${row.name}`"
      class="flex items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
    >
      <component
        :is="ICONS[row.doctype] ?? LucideSquareCheck"
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
          <span v-if="row.rule_label" class="text-ink-gray-7">{{
            row.rule_label
          }}</span>
          <EscalationBadge :level="row.level" />
          <span
            v-if="row.days && (!row.rule || row.rule === 'overdue')"
            class="font-mono text-xs tabular-nums"
          >
            {{ __("{0} working days late", String(row.days)) }}
          </span>
          <span v-if="owners(row)" class="truncate">· {{ owners(row) }}</span>
        </p>
      </div>
    </li>
  </ul>
  <p v-else class="flex items-center gap-2 px-5 py-6 text-p-sm text-ink-gray-6">
    <LucideCircleCheck class="size-4 text-success" aria-hidden="true" />
    {{ empty }}
  </p>
</template>

<script setup lang="ts">
import EscalationBadge from "@/components/EscalationBadge.vue";
import type { FollowUpRow } from "@/components/followUps";
import { __ } from "@/translation";
import type { Component } from "vue";
import { RouterLink } from "vue-router";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFolder from "~icons/lucide/folder";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTicket from "~icons/lucide/ticket";
import LucideUserRound from "~icons/lucide/user-round";

// a task unless the item is one of these
const ICONS: Record<string, Component> = {
  "HD Ticket": LucideTicket,
  // a lead: it lives on the ERP site, so the engine files it under this doctype
  "HD CRM Settings": LucideUserRound,
  Project: LucideFolder,
};

defineProps<{ rows: FollowUpRow[]; empty: string }>();

function owners(row: FollowUpRow) {
  return row.owners.map((o) => o.full_name).join(", ");
}
</script>
