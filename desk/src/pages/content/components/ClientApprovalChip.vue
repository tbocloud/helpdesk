<template>
  <span
    v-if="state"
    class="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 text-xs font-medium"
    :class="
      state === 'awaiting'
        ? 'bg-danger-soft text-danger'
        : 'bg-success-soft text-success'
    "
  >
    <component
      :is="state === 'awaiting' ? LucideClock : LucideCircleCheck"
      class="size-3.5"
      aria-hidden="true"
    />
    {{ state === "awaiting" ? __("Awaiting client") : __("Client approved") }}
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import { clientApproval } from "../constants";

// the client's side of a post's status, next to the status pill; nothing before the
// post reaches the client
const props = defineProps<{ status: string }>();
const state = computed(() => clientApproval(props.status));
</script>
