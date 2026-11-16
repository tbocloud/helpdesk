<template>
  <!-- the mail goes to a customer: who gets it, said once more -->
  <Dialog
    :open="open"
    :title="reminder ? __('Send a reminder?') : __('Send sign-off mail?')"
    size="sm"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <div class="flex flex-col gap-2 text-p-base text-ink-gray-8">
      <p>
        {{
          reminder
            ? __(
                "The same mail goes to {0} {1} again, with Reminder: before the subject.",
                name,
                `<${email}>`
              )
            : __("Send sign-off mail to {0} {1}?", name, `<${email}>`)
        }}
      </p>
      <p v-if="cc.length" class="text-p-sm text-ink-gray-6">
        {{ __("CC: {0}", cc.join(", ")) }}
      </p>
    </div>
    <template #actions>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button :label="__('Cancel')" @click="emit('update:open', false)" />
        <!-- disabled while it goes, so a second click doesn't send it twice -->
        <Button
          variant="solid"
          :label="__('Send')"
          :loading="loading"
          :disabled="loading"
          @click="emit('send')"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog } from "frappe-ui";

defineProps<{
  open: boolean;
  name: string;
  email: string;
  cc: string[];
  loading?: boolean;
  reminder?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  send: [];
}>();
</script>
