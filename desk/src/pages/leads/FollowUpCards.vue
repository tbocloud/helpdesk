<template>
  <!-- hidden quietly while the ERP site's TBO Smart can't count them, and on a failed read -->
  <div
    v-if="counts.data?.available"
    class="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4"
    role="group"
    :aria-label="__('Follow-ups by when they are due')"
  >
    <StatTile
      v-for="card in CARDS"
      :key="card.value"
      :label="card.label"
      :value="count(card.value).toLocaleString()"
      :icon="card.icon"
      :icon-tone="
        card.value === 'overdue' && count(card.value)
          ? 'danger'
          : card.value === 'today'
          ? 'warning'
          : 'info'
      "
      :value-tone="
        card.value === 'overdue' && count(card.value) ? 'danger' : 'neutral'
      "
      :pressed="due === card.value"
      @click="pick(card.value)"
    />
  </div>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import { __ } from "@/translation";
import { createResource } from "frappe-ui";
import { watch, type Component } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideSun from "~icons/lucide/sun";

export type FollowUpDue = "overdue" | "today" | "tomorrow" | "week" | "later";

const props = defineProps<{
  /** the Owner filter; a BD always sees their own */
  owner?: string;
}>();
/** the card picked ("" for none: overdue and today together, the Follow-up list) */
const due = defineModel<string>({ default: "" });

const CARDS: { value: FollowUpDue; label: string; icon: Component }[] = [
  { value: "overdue", label: __("Overdue"), icon: LucideCalendarX },
  { value: "today", label: __("Due today"), icon: LucideSun },
  { value: "tomorrow", label: __("Tomorrow"), icon: LucideCalendarClock },
  { value: "week", label: __("Next 7 days"), icon: LucideCalendarRange },
  { value: "later", label: __("Later"), icon: LucideCalendarDays },
];

// Refresh reads past the server's 60-second cache
let fresh = 0;
const counts = createResource<
  { available: boolean } & Partial<Record<FollowUpDue, number>>
>({
  url: "helpdesk.api.leads.get_follow_up_counts",
  makeParams: () => ({ owner: props.owner || null, fresh }),
  auto: true,
  onError() {},
});
watch(
  () => props.owner,
  () => counts.reload()
);

function count(value: FollowUpDue) {
  return counts.data?.[value] ?? 0;
}

/** A card shows its leads; picking it again goes back to overdue and today. */
function pick(value: FollowUpDue) {
  due.value = due.value === value ? "" : value;
}

defineExpose({
  reload() {
    fresh = 1;
    counts.reload();
    fresh = 0;
  },
});
</script>
