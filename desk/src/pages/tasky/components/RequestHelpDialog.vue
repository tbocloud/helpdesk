<template>
  <Dialog
    :open="!!task"
    :title="__('Ask a teammate for help')"
    :message="task?.subject"
    size="md"
    :dismissible="false"
    @update:open="onOpenChange"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <TeammatePicker
        v-model="teammate"
        :project="project"
        :label="__('Who can help?')"
        :exclude="task?.assignees"
      />

      <TextInput
        v-model="taskName"
        :label="__('What do you need from them?')"
        :placeholder="__('e.g. Share the customer\'s chart of accounts')"
        required
      />

      <Textarea
        v-model="description"
        :label="__('Details')"
        :placeholder="
          __('Anything that helps them do it, e.g. links or file names')
        "
        :rows="3"
      />

      <div class="flex flex-col gap-1.5">
        <TextInput
          v-model="dueDate"
          type="date"
          :label="__('Needed by')"
          :min="today"
          :max="task?.due_date || undefined"
        />
        <p class="text-p-sm text-ink-gray-5">{{ dueHint }}</p>
      </div>

      <p class="flex items-start gap-2 text-p-sm text-ink-gray-6">
        <LucideInfo
          class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{
          __(
            "They get a new task in this project. Your task waits on it, and you're told when it's done. The project lead is informed."
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
          :label="__('Ask for help')"
          :loading="requestHelp.loading"
          :disabled="!teammate || !taskName.trim()"
        >
          <template #prefix>
            <LucideUserPlus class="size-4" aria-hidden="true" />
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
  Dialog,
  TextInput,
  Textarea,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideUserPlus from "~icons/lucide/user-plus";
import TeammatePicker from "./TeammatePicker.vue";

interface HelpTask {
  name: string;
  subject?: string;
  project?: string | null;
  due_date?: string | null;
  assignees?: string[];
}

const props = defineProps<{
  /** The task that needs help; the dialog is open while this is set. */
  task: HelpTask | null;
  /** Project of the task, when the task dict doesn't carry it. */
  projectId?: string;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  requested: [result: Record<string, any>];
}>();

const formId = `tasky-request-help-${useId()}`;
const teammate = ref("");
const taskName = ref("");
const description = ref("");
const dueDate = ref("");
const today = dayjs().format("YYYY-MM-DD");

const project = computed(() => props.task?.project || props.projectId || "");

const requestHelp = createResource({
  url: "helpdesk.tasky.api.request_help",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Asked for help. Your task now waits on it."));
    emit("requested", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() => {
  const err = requestHelp.error as { messages?: string[]; message?: string };
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Couldn't ask for help.");
});

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    teammate.value = "";
    taskName.value = "";
    description.value = "";
    dueDate.value = "";
    requestHelp.reset();
  },
  { immediate: true }
);

const dueHint = computed(() =>
  props.task?.due_date
    ? __(
        "By {0} at the latest, when your task is due. Leave it empty and the AI suggests a date.",
        dayjs(props.task.due_date).format("D MMM YYYY")
      )
    : __("Leave it empty and the AI suggests a date.")
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || !teammate.value || !taskName.value.trim()) return;
  if (requestHelp.loading) return;
  requestHelp.submit({
    task: props.task.name,
    teammate: teammate.value,
    task_name: taskName.value.trim(),
    description: description.value.trim(),
    due_date: dueDate.value || null,
  });
}
</script>
