<template>
  <Dialog
    :open="!!task"
    :title="__('Hand over task')"
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
        :label="__('Hand over to')"
        :exclude="task?.assignees"
        :anyone="!!task?.content_post"
      />

      <Textarea
        v-model="reason"
        :label="__('Why?')"
        :placeholder="__('e.g. I\'m moving to the Galom go-live this week')"
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
            "The task moves to them now and leaves your lists, unless you gave it out or created it. The project lead and whoever gave you the task are told why; the lead can move it back."
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
          :label="__('Hand over')"
          :loading="handOver.loading"
          :disabled="!teammate || !reason.trim()"
        >
          <template #prefix>
            <LucideArrowRight class="size-4" aria-hidden="true" />
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
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import TeammatePicker from "./TeammatePicker.vue";

interface HandOverTask {
  name: string;
  subject?: string;
  project?: string | null;
  assignees?: string[];
  /** Set on a content post's task, which may go to anyone, not only the team. */
  content_post?: string | null;
}

const props = defineProps<{
  /** The task to hand over; the dialog is open while this is set. */
  task: HandOverTask | null;
  /** Project of the task, when the task dict doesn't carry it. */
  projectId?: string;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  handedOver: [task: Record<string, any>];
}>();

const formId = `tasky-hand-over-${useId()}`;
const teammate = ref("");
const reason = ref("");

const project = computed(() => props.task?.project || props.projectId || "");

const handOver = createResource({
  url: "helpdesk.tasky.api.hand_over_task",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Task handed over"));
    emit("handedOver", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() => {
  const err = handOver.error as { messages?: string[]; message?: string };
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Couldn't hand the task over.");
});

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    teammate.value = "";
    reason.value = "";
    handOver.reset();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || !teammate.value || !reason.value.trim()) return;
  if (handOver.loading) return;
  handOver.submit({
    task: props.task.name,
    teammate: teammate.value,
    reason: reason.value.trim(),
  });
}
</script>
