<template>
  <Dialog
    :open="!!meeting"
    :title="__('Cancel meeting?')"
    size="md"
    @update:open="(isOpen: boolean) => !isOpen && close()"
  >
    <div class="flex flex-col gap-3">
      <p class="text-p-sm text-ink-gray-7">
        {{
          meeting?.join_url
            ? __(
                "Outlook tells everyone invited that {0} is cancelled.",
                meeting?.subject || ""
              )
            : __(
                "Everyone invited is told that {0} is cancelled.",
                meeting?.subject || ""
              )
        }}
      </p>
      <Textarea
        v-model="reason"
        :label="__('Reason for cancelling')"
        :placeholder="__('Attendees will read this')"
        :rows="2"
        required
      />
    </div>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Keep it')" @click="close" />
        <Button
          variant="solid"
          theme="red"
          :label="__('Cancel meeting')"
          :loading="cancel.loading"
          :disabled="!hasReason"
          @click="confirm"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, Textarea, createResource, toast } from "frappe-ui";
import { computed, ref } from "vue";

/** the meeting to cancel; null keeps the dialog closed */
const meeting = defineModel<{
  name: string;
  subject: string;
  join_url?: string | null;
} | null>("meeting", { default: null });

const emit = defineEmits<{ cancelled: [name: string] }>();

const reason = ref("");
const hasReason = computed(() => !!reason.value.trim());

function close() {
  meeting.value = null;
  reason.value = "";
}

const cancel = createResource({
  url: "helpdesk.api.meetings.cancel_meeting",
  onSuccess(data: { name: string }) {
    toast.success(__("Meeting cancelled. Attendees have been told."));
    close();
    emit("cancelled", data.name);
  },
  onError(err: any) {
    toast.error(err?.messages?.[0] || __("Couldn't cancel the meeting."));
  },
});

function confirm() {
  if (!meeting.value || !hasReason.value) return;
  cancel.submit({ meeting: meeting.value.name, reason: reason.value.trim() });
}
</script>
