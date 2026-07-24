<template>
  <div
    v-if="show"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    @click.self="$emit('close')"
  >
    <div class="bg-surface-white border border-outline-gray-2 rounded-lg shadow-lg w-full max-w-md p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg text-ink-gray-9 font-semibold">Generate Checklist</h2>
        <button @click="$emit('close')" class="text-ink-gray-6 hover:text-ink-gray-9">
          <LucideX class="size-5" />
        </button>
      </div>

      <div v-if="templates.loading" class="text-ink-gray-6 text-sm py-4">Loading templates...</div>
      <div v-else-if="templates.error" class="text-red-500 text-sm py-4">{{ templates.error }}</div>
      <div v-else>
        <label class="block text-sm text-ink-gray-7 mb-2">Select Implementation Template</label>
        <select
          v-model="selectedTemplate"
          class="w-full border border-outline-gray-2 rounded-md px-3 py-2 text-sm text-ink-gray-9 bg-surface-white mb-4"
        >
          <option value="" disabled>Choose a template...</option>
          <option
            v-for="t in templates.data"
            :key="t.name"
            :value="t.name"
          >
            {{ t.template_name }} {{ t.industry ? `(${t.industry})` : '' }}
          </option>
        </select>

        <div v-if="generateTask.loading" class="text-ink-gray-6 text-sm py-2">Generating tasks...</div>
        <div v-else-if="generateTask.error" class="text-red-500 text-sm py-2">{{ generateTask.error }}</div>
        <div v-else-if="generateTask.data" class="text-green-600 text-sm py-2">
          {{ generateTask.data.tasks_created }} tasks created!
        </div>

        <div class="flex justify-end gap-2 mt-4">
          <button
            @click="$emit('close')"
            class="px-4 py-2 text-sm text-ink-gray-7 bg-surface-gray-2 rounded-md hover:bg-surface-gray-3"
          >
            Cancel
          </button>
          <button
            @click="generate"
            :disabled="!selectedTemplate || generateTask.loading"
            class="px-4 py-2 text-sm text-white bg-gray-800 rounded-md hover:bg-gray-900 disabled:opacity-50"
          >
            Generate
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { createListResource, createResource } from "frappe-ui";
import LucideX from "~icons/lucide/x";

const props = defineProps<{
  show: boolean;
  projectId: string;
}>();

const emit = defineEmits<{
  close: [];
  generated: [];
}>();

const selectedTemplate = ref("");

const templates = createListResource({
  doctype: "Tasky Template",
  fields: ["name", "template_name", "industry", "description"],
  auto: true,
});

const generateTask = createResource({
  url: "helpdesk.tasky.api.generate_checklist",
  onSuccess() {
    setTimeout(() => emit("generated"), 1000);
  },
});

function generate() {
  if (!selectedTemplate.value) return;
  generateTask.submit({
    project: props.projectId,
    template: selectedTemplate.value,
  });
}
</script>
