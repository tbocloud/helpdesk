<template>
  <Dialog
    :open="!!task"
    :title="__('Resume task')"
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
      <div
        class="flex flex-col gap-1 rounded-md bg-warning-soft px-3 py-2.5 text-sm text-warning"
      >
        <span class="flex items-center gap-2 font-medium">
          <LucidePause class="size-4 shrink-0" aria-hidden="true" />
          <span class="tabular-nums">{{ holdDurationLabel(days) }}</span>
          <template v-if="task?.hold_reason">
            <span aria-hidden="true">·</span>
            <span>{{ __(task.hold_reason) }}</span>
          </template>
        </span>
        <p v-if="task?.hold_note" class="pl-6 text-p-sm text-ink-gray-7">
          {{ task.hold_note }}
        </p>
        <p
          v-if="task && holdByLabel(task)"
          class="pl-6 text-p-sm tabular-nums text-ink-gray-5"
        >
          {{ holdByLabel(task) }}
        </p>
      </div>

      <div v-if="canExtend" class="flex flex-col gap-1.5">
        <Checkbox
          v-model="extendDueDate"
          :label="
            days === 1
              ? __('Move the due date by 1 day')
              : __('Move the due date by {0} days', String(days))
          "
        />
        <p class="pl-6 text-p-sm tabular-nums text-ink-gray-5">
          <template v-if="extendDueDate">
            {{ __("Due {0} → {1}", formatDate(task?.due_date), newDueDate) }}
          </template>
          <template v-else>
            {{ __("Stays due {0}", formatDate(task?.due_date)) }}
          </template>
        </p>
      </div>

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
          :label="__('Resume')"
          :loading="resumeTask.loading"
        >
          <template #prefix>
            <LucidePlay class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Checkbox,
  Dialog,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePause from "~icons/lucide/pause";
import LucidePlay from "~icons/lucide/play";
import { holdByLabel, holdDays, holdDurationLabel } from "../taskMeta";

interface HeldTask {
  name: string;
  subject?: string;
  due_date?: string | null;
  hold_reason?: string | null;
  hold_note?: string | null;
  hold_since?: string | null;
  hold_by_name?: string | null;
}

const props = defineProps<{
  /** The on-hold task to resume; the dialog is open while this is set. */
  task: HeldTask | null;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  resumed: [task: Record<string, any>];
}>();

const formId = `tasky-resume-task-${useId()}`;
const extendDueDate = ref(true);

const days = computed(() => (props.task ? holdDays(props.task) : 0));
const canExtend = computed(() => !!props.task?.due_date && days.value > 0);
const newDueDate = computed(() =>
  props.task?.due_date
    ? formatDate(dayjs(props.task.due_date).add(days.value, "day").toString())
    : ""
);

function formatDate(date?: string | null) {
  return date ? dayjs(date).format("D MMM YYYY") : "—";
}

const resumeTask = createResource({
  url: "helpdesk.tasky.api.resume_task",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Task resumed"));
    emit("resumed", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() => {
  const err = resumeTask.error as { messages?: string[]; message?: string };
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Couldn't resume the task.");
});

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    extendDueDate.value = true;
    resumeTask.reset();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || resumeTask.loading) return;
  resumeTask.submit({
    task: props.task.name,
    extend_due_date: canExtend.value ? extendDueDate.value : false,
  });
}
</script>
