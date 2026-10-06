<template>
  <ul v-if="items.length" role="list">
    <li
      v-for="item in items"
      :key="itemKey(item)"
      class="flex items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
    >
      <component
        :is="item.kind === 'ticket' ? LucideTicket : LucideSquareCheck"
        class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
        aria-hidden="true"
      />
      <div class="min-w-0 flex-1">
        <span class="sr-only">{{
          item.kind === "ticket" ? __("Ticket") : __("Task")
        }}</span>
        <RouterLink
          v-if="itemRoute(item)"
          :to="itemRoute(item)!"
          class="block truncate rounded text-base text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ item.title }}
        </RouterLink>
        <span v-else class="block truncate text-base text-ink-gray-9">
          {{ item.title }}
        </span>
        <!-- why it's flagged, then where and who -->
        <p class="mt-0.5 flex min-w-0 items-center gap-1.5 text-sm">
          <span
            class="inline-flex shrink-0 items-center gap-1"
            :class="reason(item).overdue ? 'text-danger' : 'text-warning'"
          >
            <component
              :is="
                reason(item).overdue ? LucideAlarmClock : LucideTriangleAlert
              "
              class="size-3.5 shrink-0"
              aria-hidden="true"
            />
            {{ reason(item).label }}
          </span>
          <span
            v-if="context(item)"
            class="truncate text-ink-gray-5"
            :title="context(item)"
          >
            · {{ context(item) }}
          </span>
        </p>
      </div>
      <RouterLink
        v-if="item.summary"
        :to="{ name: 'WorkSummary', params: { name: item.summary.name } }"
        class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded text-sm text-ink-gray-7 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :aria-label="__('Latest work summary for {0}', item.customer || '')"
      >
        <LucideFileText class="size-3.5" aria-hidden="true" />
        <span class="hidden sm:inline">{{ __("Summary") }}</span>
      </RouterLink>
    </li>
  </ul>
  <p v-else class="flex items-center gap-2 px-4 py-6 text-p-sm text-ink-gray-6">
    <LucideCircleCheck class="size-4 text-success" aria-hidden="true" />
    {{ __("Nothing is overdue or likely to slip right now.") }}
  </p>
</template>

<script setup lang="ts">
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFileText from "~icons/lucide/file-text";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTicket from "~icons/lucide/ticket";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { AttentionItem } from "../overviewMeta";
import { deadlineInfo, itemKey, itemRoute } from "../workMeta";

defineProps<{ items: AttentionItem[] }>();
const userStore = useUserStore();

function reason(item: AttentionItem) {
  if (item.is_overdue)
    return { label: deadlineInfo(item).label, overdue: true };
  return { label: item.risks?.[0] ?? __("At risk"), overdue: false };
}

function context(item: AttentionItem) {
  const where =
    item.kind === "ticket"
      ? item.customer
      : item.project_name || item.project || item.customer;
  const who = item.assignees.length
    ? item.assignees.map((u) => userStore.getUser(u)?.full_name || u).join(", ")
    : __("Unassigned");
  return [where, who].filter(Boolean).join(" · ");
}
</script>
