<template>
  <!-- move a row up or down the list, or take it off -->
  <div class="flex shrink-0 items-center gap-1">
    <Button
      variant="ghost"
      :aria-label="__('Move {0} up', [label])"
      :disabled="first"
      @click="emit('move', -1)"
    >
      <template #icon>
        <LucideArrowUp class="size-4" aria-hidden="true" />
      </template>
    </Button>
    <Button
      variant="ghost"
      :aria-label="__('Move {0} down', [label])"
      :disabled="last"
      @click="emit('move', 1)"
    >
      <template #icon>
        <LucideArrowDown class="size-4" aria-hidden="true" />
      </template>
    </Button>
    <Button
      variant="ghost"
      :aria-label="__('Remove {0}', [label])"
      @click="emit('remove')"
    >
      <template #icon>
        <LucideX class="size-4" aria-hidden="true" />
      </template>
    </Button>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideX from "~icons/lucide/x";

defineProps<{ label: string; first: boolean; last: boolean }>();
const emit = defineEmits<{ move: [delta: number]; remove: [] }>();
</script>
