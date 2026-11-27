<template>
  <Dialog
    :open="!!task"
    :title="__('Decline the extra hours')"
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
        :label="__('Why aren\'t they approved?')"
        :placeholder="
          __('e.g. Out of the agreed scope; raise a change request')
        "
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
            "The {0} h over the estimate are never logged. The task completes with the hours within the estimate, and {1} is told why.",
            String(task?.extra_hours || 0),
            task?.extra_hours_by_name || __("the assignee")
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
          :label="__('Decline and complete')"
          :loading="decline.loading"
          :disabled="!note.trim()"
        />
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

interface ExtraHoursTask {
  name: string;
  subject?: string;
  extra_hours?: number;
  extra_hours_by_name?: string | null;
}

const props = defineProps<{
  /** The Pending Review task whose extra hours to decline; open while this is set. */
  task: ExtraHoursTask | null;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  declined: [task: Record<string, any>];
}>();

const formId = `tasky-decline-extra-${useId()}`;
const note = ref("");

const decline = createResource({
  url: "helpdesk.tasky.api.decline_extra_hours",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Extra hours declined; the task is completed"));
    emit("declined", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  decline.error
    ? errorText(decline.error, __("Couldn't decline the extra hours."))
    : ""
);

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    note.value = "";
    decline.reset();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || !note.value.trim() || decline.loading) return;
  decline.submit({ task: props.task.name, note: note.value.trim() });
}
</script>
