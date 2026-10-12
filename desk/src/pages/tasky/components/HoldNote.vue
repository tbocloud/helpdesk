<template>
  <!-- shown under the hold pill so the "why" is readable without hovering;
       a long note is clamped here and shown in full in the task's details -->
  <div v-if="note || byName" class="min-w-0 text-p-xs">
    <p
      v-if="note"
      class="line-clamp-2 break-words text-ink-gray-7"
      :title="note"
    >
      {{ note }}
    </p>
    <p v-if="byName" class="truncate text-ink-gray-5">
      {{ __("Put on hold by {0}", byName) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";

defineProps<{
  /** What the person wrote when putting the task on hold. */
  note?: string | null;
  /** Full name of whoever put it on hold. */
  byName?: string | null;
}>();
</script>
