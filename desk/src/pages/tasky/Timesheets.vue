<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header><div class="text-lg-medium text-ink-gray-9">{{ __("Timesheets") }}</div></template>
    </LayoutHeader>
    <div class="flex-1 overflow-auto p-5">
      <div v-if="timesheets.loading" class="flex items-center justify-center h-64"><div class="text-p-base text-ink-gray-6">Loading...</div></div>
      <div v-else-if="!timesheets.data?.length" class="flex items-center justify-center h-64">
        <div class="flex flex-col items-center gap-2"><LucideClock class="size-12 text-ink-gray-4" /><div class="text-lg-medium text-ink-gray-6">No timesheets yet</div></div>
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="ts in timesheets.data" :key="ts.name" class="bg-surface-white border border-outline-gray-2 rounded-lg p-4">
          <div class="text-sm-medium text-ink-gray-9 truncate mb-1">{{ ts.title || ts.name }}</div>
          <div class="flex items-center gap-3 text-xs text-ink-gray-5">
            <span class="px-2 py-0.5 rounded-full" :class="ts.status === 'Submitted' ? 'bg-ink-green-1 text-ink-green-8' : 'bg-ink-amber-1 text-ink-amber-8'">{{ ts.status }}</span>
            <span>{{ ts.total_hours || 0 }}h</span>
            <span>{{ formatDate(ts.modified) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import LucideClock from "~icons/lucide/clock";

const timesheets = createResource({
  url: "helpdesk.tasky.api.get_my_timesheets",
  auto: true,
  transform: (d: any[]) => d ?? [],
});

function formatDate(d: string) { return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
</script>
