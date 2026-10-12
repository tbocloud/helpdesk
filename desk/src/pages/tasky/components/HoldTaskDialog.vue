<template>
  <Dialog
    :open="!!task"
    :title="__('Put task on hold')"
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
      <fieldset class="flex flex-col gap-1.5">
        <legend class="mb-1.5 text-xs text-ink-gray-5">
          {{ __("Reason") }}
          <span class="text-danger" aria-hidden="true">*</span>
        </legend>
        <label
          v-for="option in HOLD_REASONS"
          :key="option"
          class="flex cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors focus-within:ring-2 focus-within:ring-outline-gray-4"
          :class="
            reason === option
              ? 'border-outline-gray-4 bg-surface-gray-1 text-ink-gray-9'
              : 'border-outline-gray-2 text-ink-gray-7 hover:border-outline-gray-3'
          "
        >
          <input
            v-model="reason"
            type="radio"
            :name="`${formId}-reason`"
            :value="option"
            class="size-4 accent-brand focus:outline-none"
            required
          />
          {{ __(option) }}
        </label>
      </fieldset>

      <Textarea
        v-model="note"
        :label="noteRequired ? __('Why is it on hold?') : __('Note')"
        :required="noteRequired"
        :error="noteError"
        :placeholder="
          noteRequired
            ? __('Say what is blocking the task')
            : __('Optional details, e.g. when you expect to be back')
        "
        :rows="2"
        @blur="noteTouched = true"
      />

      <p class="flex items-start gap-2 text-p-sm text-ink-gray-6">
        <LucideInfo
          class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{
          __(
            "The task won't count as overdue while it's on hold. When it resumes, the days on hold are added to the due date."
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
          :label="__('Put on hold')"
          :loading="holdTask.loading"
          :disabled="!canSubmit"
        >
          <template #prefix>
            <LucidePause class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, Textarea, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucidePause from "~icons/lucide/pause";
import { HOLD_REASONS } from "../taskMeta";

interface HoldableTask {
  name: string;
  subject?: string;
}

const props = defineProps<{
  /** The task to put on hold; the dialog is open while this is set. */
  task: HoldableTask | null;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  held: [task: Record<string, any>];
}>();

const formId = `tasky-hold-task-${useId()}`;
const reason = ref("");
const note = ref("");
const noteTouched = ref(false);

// "Other" says nothing on its own, so the board can only explain the hold with a note
// (hold_task refuses it too)
const noteRequired = computed(() => reason.value === "Other");
const noteMissing = computed(() => noteRequired.value && !note.value.trim());
const noteError = computed(() =>
  noteMissing.value && noteTouched.value
    ? __("Say what is blocking the task.")
    : undefined
);
const canSubmit = computed(() => !!reason.value && !noteMissing.value);

const holdTask = createResource({
  url: "helpdesk.tasky.api.hold_task",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Task put on hold"));
    emit("held", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() => {
  const err = holdTask.error as { messages?: string[]; message?: string };
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Couldn't put the task on hold.");
});

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    reason.value = "";
    note.value = "";
    noteTouched.value = false;
    holdTask.reset();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || holdTask.loading) return;
  if (!canSubmit.value) {
    noteTouched.value = true;
    return;
  }
  holdTask.submit({
    task: props.task.name,
    reason: reason.value,
    note: note.value.trim(),
  });
}
</script>
