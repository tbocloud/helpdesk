<template>
  <!-- the inbox's middle before a ticket is opened (Phase 16): opening one marks it seen, so none
       opens by itself -->
  <div
    class="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
  >
    <span
      class="flex size-12 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5"
    >
      <LucideMessagesSquare class="size-6" aria-hidden="true" />
    </span>
    <p class="text-lg font-medium text-ink-gray-9">
      {{ __("Pick a ticket to see its conversation") }}
    </p>
    <p class="max-w-sm text-base text-ink-gray-6">
      {{
        __(
          "The customer's messages, the team's notes and Copilot's work, in one thread."
        )
      }}
    </p>
    <p class="text-sm text-ink-gray-5">
      <kbd class="rounded border border-outline-gray-2 px-1 font-mono text-2xs"
        >J</kbd
      >
      /
      <kbd class="rounded border border-outline-gray-2 px-1 font-mono text-2xs"
        >K</kbd
      >
      {{ __("move between tickets") }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import LucideMessagesSquare from "~icons/lucide/messages-square";
</script>
