<template>
  <!-- the morning's one ask: check the filled-in stand-up and submit it -->
  <section
    class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
    :aria-label="__('Your stand-up')"
  >
    <LucideMessagesSquare
      class="size-5 shrink-0 text-ink-gray-5"
      aria-hidden="true"
    />
    <div class="min-w-0 flex-1">
      <p class="text-base-medium text-ink-gray-9">
        {{ __("Your stand-up is ready") }}
      </p>
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Filled in from your work. Check it and submit (1 min); it goes to your team at {0}.",
            standup.post_at
          )
        }}
      </p>
    </div>
    <Button
      variant="solid"
      class="!h-11 max-sm:w-full"
      :label="__('Open stand-up')"
      @click="router.push({ name: 'Standup' })"
    />
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { useRouter } from "vue-router";
import LucideMessagesSquare from "~icons/lucide/messages-square";

defineProps<{ standup: { name: string; date: string; post_at: string } }>();

const router = useRouter();
</script>
