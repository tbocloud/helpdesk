<template>
  <div
    class="grid h-full place-items-center px-4 py-20 text-center text-lg text-ink-gray-5"
  >
    <div
      class="w-full max-w-md space-y-4 rounded-xl border border-outline-gray-2 bg-surface-base px-6 py-10"
    >
      <div class="flex justify-center items-center mx-auto">
        <LucideFileX class="size-10 text-ink-gray-4" />
      </div>
      <div class="flex flex-col gap-1">
        <h1 class="text-xl font-bold text-ink-gray-9">
          {{ __("Page not found") }}
        </h1>
        <div class="text-center text-p-base text-ink-gray-6 mt-1">
          {{
            __(
              "You don't have permission to view this page, or it no longer exists."
            )
          }}
        </div>
      </div>
      <Button :route="{ name: 'TicketsAgent' }" size="md">
        <template #prefix>
          <FeatherIcon name="arrow-left" class="size-4" />
        </template>
        {{ __("Back to Tickets") }}
      </Button>
    </div>
  </div>
</template>

<script setup>
import { Button, FeatherIcon } from "frappe-ui";
import { __ } from "@/translation";
</script>
