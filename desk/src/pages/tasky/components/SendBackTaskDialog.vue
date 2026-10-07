<template>
  <Dialog
    :open="!!task"
    :title="__('Send back for changes')"
    :message="task?.subject"
    size="md"
    @update:open="onOpenChange"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <Textarea
        v-model="note"
        :label="__('What still needs doing?')"
        :placeholder="__('e.g. The import skipped the closing balances')"
        :rows="3"
        required
      />
      <p class="flex items-start gap-2 text-p-sm text-ink-gray-6">
        <LucideInfo
          class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{
          __(
            "The task goes back to Open and the assignee is notified with your note."
          )
        }}
      </p>

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Send back')"
          :loading="sendBack.loading"
          :disabled="!note.trim()"
        >
          <template #prefix>
            <LucideUndo2 class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { __ } from "@/translation";
import { Button, Dialog, Textarea, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideUndo2 from "~icons/lucide/undo-2";

interface ReviewedTask {
  name: string;
  subject?: string;
}

const props = defineProps<{
  /** The Pending Review task to return; the dialog is open while this is set. */
  task: ReviewedTask | null;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  sent: [task: Record<string, any>];
}>();

const formId = `tasky-send-back-${useId()}`;
const note = ref("");

const sendBack = createResource({
  url: "helpdesk.tasky.api.send_back_task",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Task sent back"));
    emit("sent", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  sendBack.error
    ? errorText(sendBack.error, __("Couldn't send the task back."))
    : ""
);

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    note.value = "";
    sendBack.reset();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || !note.value.trim() || sendBack.loading) return;
  sendBack.submit({ task: props.task.name, note: note.value.trim() });
}
</script>
