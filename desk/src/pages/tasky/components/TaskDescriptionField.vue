<template>
  <div class="flex flex-col gap-1.5">
    <div class="flex min-h-7 flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <label :for="inputId" class="block text-base text-ink-gray-5">
          {{ __("Description") }}
        </label>
        <AiDraftedChip v-if="aiDrafted" />
      </div>
      <Button
        variant="ghost"
        size="sm"
        :label="__('Write with AI')"
        :loading="draft.loading"
        :disabled="!canDraft"
        :title="unavailableReason || undefined"
        :aria-describedby="aiUnavailable ? hintId : undefined"
        @click="onWrite"
      >
        <template #prefix>
          <LucideSparkles class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <Textarea
      :id="inputId"
      :model-value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      :autofocus="autofocus"
      :disabled="draft.loading"
      @update:model-value="(v: string) => emit('update:modelValue', v)"
    />

    <p v-if="aiUnavailable" :id="hintId" class="text-p-xs text-ink-gray-5">
      {{ status.data?.reason }}
    </p>

    <div
      v-if="choosing"
      role="group"
      :aria-label="__('Where the AI draft goes')"
      class="flex flex-wrap items-center gap-2 rounded-md bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
    >
      <span class="me-auto">{{
        __("The description already has text. Use the AI draft how?")
      }}</span>
      <Button size="sm" :label="__('Replace')" @click="write('replace')" />
      <Button size="sm" :label="__('Add below')" @click="write('append')" />
      <Button
        size="sm"
        variant="ghost"
        :label="__('Cancel')"
        @click="choosing = false"
      />
    </div>

    <div
      v-if="draftError"
      role="alert"
      class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{{ draftError }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Textarea, createResource } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideSparkles from "~icons/lucide/sparkles";
import { errorText, isAiDrafted } from "../taskMeta";
import AiDraftedChip from "./AiDraftedChip.vue";

/** What the AI is told about the task; task_name is required, task is set when editing. */
export interface DraftContext {
  task_name: string;
  project?: string;
  task?: string;
  category?: string;
  phase?: string;
  priority?: string;
  estimated_hours?: number;
  assigned_to?: string;
}

const props = withDefaults(
  defineProps<{
    modelValue: string;
    /** The text the AI wrote, while it may still be in the box; null when none. */
    aiText: string | null;
    context: DraftContext;
    placeholder?: string;
    rows?: number;
    autofocus?: boolean;
  }>(),
  { rows: 3 }
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  "update:aiText": [value: string | null];
}>();

const inputId = `task-description-${useId()}`;
const hintId = `${inputId}-ai-hint`;
const choosing = ref(false);
const mode = ref<"replace" | "append">("replace");

const status = createResource({
  url: "helpdesk.task_descriptions.get_ai_status",
  cache: "tasky-ai-description-status",
  auto: true,
});

const draft = createResource({
  url: "helpdesk.task_descriptions.draft_task_description",
  onSuccess(data: { description: string }) {
    const current = props.modelValue.trimEnd();
    const text =
      mode.value === "append" && current
        ? `${current}\n\n${data.description}`
        : data.description;
    emit("update:modelValue", text);
    emit("update:aiText", text);
  },
  // shown under the box instead of the global error toast
  onError() {},
});

const aiDrafted = computed(() => isAiDrafted(props.modelValue, props.aiText));
const aiUnavailable = computed(() => status.data?.available === false);
const hasName = computed(() => !!props.context.task_name?.trim());

const unavailableReason = computed(() => {
  if (aiUnavailable.value) return status.data?.reason as string;
  if (!hasName.value) return __("Type the task name first");
  return "";
});

const canDraft = computed(
  () => hasName.value && status.data?.available === true && !draft.loading
);

const draftError = computed(() =>
  draft.error
    ? errorText(draft.error, __("The AI couldn't write a description."))
    : ""
);

function onWrite() {
  if (!canDraft.value) return;
  if (props.modelValue.trim()) {
    choosing.value = true;
    return;
  }
  write("replace");
}

function write(how: "replace" | "append") {
  choosing.value = false;
  mode.value = how;
  draft.submit({ ...props.context, task_name: props.context.task_name.trim() });
}
</script>
