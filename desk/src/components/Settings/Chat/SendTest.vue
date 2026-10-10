<template>
  <div class="flex flex-col items-start gap-1.5">
    <Button
      :label="label"
      :loading="test.loading"
      :disabled="unsaved"
      :tooltip="unsaved ? __('Save your changes first') : ''"
      @click="test.submit()"
    >
      <template #prefix>
        <LucideSend class="size-4" aria-hidden="true" />
      </template>
    </Button>
    <p
      v-if="result"
      role="status"
      class="flex items-start gap-1.5 text-p-sm"
      :class="result.ok ? 'text-success' : 'text-danger'"
    >
      <component
        :is="result.ok ? LucideCircleCheck : LucideCircleAlert"
        class="mt-0.5 size-4 shrink-0"
        aria-hidden="true"
      />
      <span>{{ result.message }}</span>
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { computed } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideSend from "~icons/lucide/send";

const props = defineProps<{
  target: "direct" | "channel";
  label: string;
  /** The test uses the saved settings, so it waits until they are saved. */
  unsaved?: boolean;
}>();

const test = createResource({
  url: "helpdesk.api.chat_settings.send_test",
  makeParams: () => ({ target: props.target }),
});

const result = computed<{ ok: boolean; message: string } | null>(() => {
  if (test.error)
    return {
      ok: false,
      message: test.error.messages?.[0] || __("Couldn't send the test message"),
    };
  return test.data || null;
});
</script>
