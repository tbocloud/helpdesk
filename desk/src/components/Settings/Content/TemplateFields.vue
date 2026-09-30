<template>
  <details class="group rounded-lg border border-outline-gray-2">
    <summary
      class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-base-medium text-ink-gray-8"
    >
      <LucideChevronRight
        class="size-4 text-ink-gray-5 transition-transform group-open:rotate-90"
        aria-hidden="true"
      />
      {{ title }}
      <span class="text-p-sm text-ink-gray-5">
        {{ subject || message ? __("Customised") : __("Default") }}
      </span>
    </summary>
    <div class="flex flex-col gap-3 border-t border-outline-gray-2 p-3">
      <p v-if="defaults" class="text-p-sm text-ink-gray-6">
        {{ __("Leave blank to use the default. Placeholders:") }}
        <code
          v-for="p in defaults.placeholders"
          :key="p"
          class="ms-1 rounded bg-surface-gray-2 px-1 font-mono text-xs text-ink-gray-8"
          v-text="'{' + p + '}'"
        />
      </p>
      <FormControl
        v-model="subject"
        :label="__('Subject')"
        :placeholder="defaults?.subject"
      />
      <FormControl
        v-model="message"
        type="textarea"
        :rows="6"
        class="font-mono"
        :label="__('Message (HTML)')"
        :placeholder="defaults?.message"
      />
      <div class="flex justify-end">
        <Button
          v-if="subject || message"
          size="sm"
          variant="ghost"
          :label="__('Reset to default')"
          @click="reset"
        />
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import LucideChevronRight from "~icons/lucide/chevron-right";

defineProps<{
  title: string;
  defaults?: { subject: string; message: string; placeholders: string[] };
}>();
const subject = defineModel<string>("subject", { default: "" });
const message = defineModel<string>("message", { default: "" });

function reset() {
  subject.value = "";
  message.value = "";
}
</script>
