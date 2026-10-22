<template>
  <span
    v-if="icon"
    class="grid size-8 shrink-0 place-items-center rounded-full"
    :class="icon.tone"
    aria-hidden="true"
  >
    <component :is="icon.component" class="size-4" />
  </span>
  <UserAvatar v-else :name="notification.user_from" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { UserAvatar } from "@/components";
import { Notification } from "@/types";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideTicket from "~icons/lucide/ticket";
import LucideTicketPlus from "~icons/lucide/ticket-plus";

const props = defineProps<{ notification: Notification }>();

// a reminder is about time (warning); ticket notices carry no status, so stay neutral
const NEUTRAL = "bg-surface-gray-2 text-ink-gray-7";
const ICONS = {
  Reminder: {
    component: LucideAlarmClock,
    tone: "bg-warning-soft text-warning",
  },
  "New Ticket": { component: LucideTicketPlus, tone: NEUTRAL },
  "Ticket Update": { component: LucideTicket, tone: NEUTRAL },
};

const icon = computed(() => ICONS[props.notification.notification_type]);
</script>
