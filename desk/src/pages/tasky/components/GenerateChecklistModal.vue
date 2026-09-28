<template>
  <Dialog
    :open="show"
    :title="__('Generate checklist')"
    :message="
      hasTemplates
        ? __('Create this project\'s tasks from a template.')
        : undefined
    "
    size="md"
    @update:open="(value: boolean) => !value && emit('close')"
  >
    <div
      v-if="templates.loading && !templates.data"
      class="flex flex-col gap-2 py-1"
    >
      <div class="h-3 w-16 animate-pulse rounded bg-surface-gray-2" />
      <div class="h-7 animate-pulse rounded bg-surface-gray-2" />
    </div>

    <div
      v-else-if="templates.error"
      role="alert"
      class="flex flex-col items-start gap-3 rounded-md bg-surface-gray-1 p-3"
    >
      <div class="flex items-center gap-2 text-p-sm text-ink-gray-7">
        <LucideCircleAlert
          class="size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{ __("Couldn't load templates.") }}
      </div>
      <Button :label="__('Retry')" @click="templates.reload()" />
    </div>

    <div
      v-else-if="!hasTemplates"
      class="flex flex-col items-center gap-2 px-2 py-6 text-center"
    >
      <div
        class="mb-1 flex size-12 items-center justify-center rounded-full bg-surface-gray-2"
      >
        <LucideClipboardList
          class="size-5 text-ink-gray-6"
          aria-hidden="true"
        />
      </div>
      <div class="text-base-medium text-ink-gray-8">
        {{ __("No templates yet") }}
      </div>
      <p class="max-w-xs text-p-sm text-ink-gray-6">
        {{
          __(
            "Templates turn a standard implementation plan into tasks in one go. You can also add tasks one at a time."
          )
        }}
      </p>
      <div class="mt-2 flex flex-wrap justify-center gap-2">
        <Button
          v-if="authStore.isProjectManager"
          :label="__('Create a template')"
          @click="goToTemplates"
        />
        <Button
          variant="solid"
          :label="__('Add a single task')"
          @click="emit('addTask')"
        >
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </div>
    </div>

    <div v-else class="flex flex-col gap-3">
      <FormControl
        v-model="selectedTemplate"
        type="select"
        :label="__('Template')"
        :placeholder="__('Select a template…')"
        :options="templateOptions"
      />

      <p
        v-if="selected"
        class="rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-7"
      >
        {{
          selected.description ||
          __("{0} implementation template", selected.industry || __("General"))
        }}
      </p>

      <div
        v-if="generateTask.error"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ errorText(generateTask.error) }}
      </div>
      <div
        v-else-if="generateTask.data"
        role="status"
        class="flex items-center gap-2 rounded-md bg-success-soft px-3 py-2 text-p-sm text-success"
      >
        <LucideCircleCheck class="size-4 shrink-0" aria-hidden="true" />
        {{ __("{0} tasks created", String(generateTask.data.tasks_created)) }}
      </div>
    </div>

    <template v-if="hasTemplates" #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          :label="__('Generate')"
          :loading="generateTask.loading"
          :disabled="!selectedTemplate || !!generateTask.data"
          @click="generate"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, Dialog, FormControl, createResource } from "frappe-ui";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucidePlus from "~icons/lucide/plus";

const props = defineProps<{
  show: boolean;
  projectId: string;
}>();

const emit = defineEmits<{
  close: [];
  generated: [];
  addTask: [];
}>();

const router = useRouter();
const authStore = useAuthStore();
const selectedTemplate = ref("");

const templates = createResource({
  url: "helpdesk.tasky.api.get_templates",
  auto: true,
  transform: (d: any) => d ?? [],
});

const hasTemplates = computed(() => !!templates.data?.length);
const templateOptions = computed(() =>
  (templates.data ?? []).map((t: any) => ({
    label: t.industry ? `${t.template_name} · ${t.industry}` : t.template_name,
    value: t.name,
  }))
);
const selected = computed(() =>
  (templates.data ?? []).find((t: any) => t.name === selectedTemplate.value)
);

const generateTask = createResource({
  url: "helpdesk.tasky.api.generate_checklist",
  onSuccess() {
    // brief pause so the "N tasks created" confirmation is readable before closing
    setTimeout(() => emit("generated"), 800);
  },
  onError() {},
});

function errorText(err: { messages?: string[]; message?: string }) {
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Couldn't generate the checklist.");
}

function generate() {
  if (!selectedTemplate.value) return;
  generateTask.submit({
    project: props.projectId,
    template: selectedTemplate.value,
  });
}

function goToTemplates() {
  emit("close");
  router.push({ name: "TaskyTemplates" });
}
</script>
