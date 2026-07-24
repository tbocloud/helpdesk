<template>
  <div class="flex flex-col h-full">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Templates") }}</div>
      </template>
      <template #right-header>
        <button class="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-surface-gray-3 text-ink-gray-8 hover:bg-surface-gray-4 transition-colors" @click="showForm = !showForm">
          <Plus class="size-4" /> {{ __("New Template") }}
        </button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto p-5">
      <div v-if="showForm" class="bg-surface-white border border-outline-gray-2 rounded-lg p-5 mb-6">
        <div class="text-sm-medium text-ink-gray-8 mb-4">{{ __("New Template") }}</div>
        <div class="grid grid-cols-2 gap-4 mb-4">
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">Template Name</label>
            <input v-model="form.template_name" class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none focus:border-outline-gray-3" placeholder="e.g. Retail Implementation" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs text-ink-gray-5">Industry</label>
            <input v-model="form.industry" class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none focus:border-outline-gray-3" placeholder="e.g. Retail, Manufacturing" />
          </div>
          <div class="flex flex-col gap-1 col-span-2">
            <label class="text-xs text-ink-gray-5">Description</label>
            <textarea v-model="form.description" rows="2" class="border border-outline-gray-2 rounded px-3 py-1.5 text-sm bg-surface-white focus:outline-none focus:border-outline-gray-3" placeholder="Brief description" />
          </div>
        </div>

        <div class="text-xs font-medium text-ink-gray-6 mb-2">Tasks</div>
        <div class="bg-surface-gray-1 rounded-lg p-3 mb-2">
          <div v-for="(task, idx) in form.tasks" :key="idx" class="flex items-center gap-2 mb-2 last:mb-0">
            <input v-model="task.task_name" placeholder="Task name" class="flex-1 border border-outline-gray-2 rounded px-2 py-1 text-sm bg-surface-white focus:outline-none" />
            <input v-model="task.phase_name" placeholder="Phase" class="w-28 border border-outline-gray-2 rounded px-2 py-1 text-sm bg-surface-white focus:outline-none" />
            <select v-model="task.category" class="w-28 border border-outline-gray-2 rounded px-2 py-1 text-sm bg-surface-white"><option>Functional</option><option>Development</option><option>Support</option><option>Common</option></select>
            <select v-model="task.default_priority" class="w-20 border border-outline-gray-2 rounded px-2 py-1 text-sm bg-surface-white"><option>High</option><option>Medium</option><option>Low</option><option>Urgent</option></select>
            <input v-model.number="task.estimated_hours" type="number" placeholder="Hrs" class="w-14 border border-outline-gray-2 rounded px-2 py-1 text-sm bg-surface-white" />
            <button @click="form.tasks.splice(idx, 1)" class="size-6 flex items-center justify-center rounded text-ink-gray-5 hover:text-ink-red-6"><LucideX class="size-3.5" /></button>
          </div>
          <button @click="addTaskRow" class="flex items-center gap-1 text-xs text-ink-gray-5 hover:text-ink-gray-8 mt-1"><LucidePlus class="size-3.5" /> Add row</button>
        </div>

        <div class="flex items-center gap-2">
          <button class="px-4 py-1.5 rounded text-sm bg-surface-gray-3 text-ink-gray-8 hover:bg-surface-gray-4 disabled:opacity-50" :disabled="!form.template_name || save.loading" @click="onSave">{{ save.loading ? "Saving..." : "Save Template" }}</button>
          <button class="px-4 py-1.5 rounded text-sm text-ink-gray-6 hover:text-ink-gray-8" @click="showForm = false">Cancel</button>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="t in templates.data" :key="t.name" class="bg-surface-white border border-outline-gray-2 rounded-lg p-5 hover:shadow-md transition-shadow">
          <div class="text-base-semibold text-ink-gray-9 mb-1">{{ t.template_name }}</div>
          <div class="text-xs text-ink-gray-5 mb-3">{{ t.industry || "General" }} · {{ t.description || "No description" }}</div>
          <span class="text-xs text-ink-gray-6 bg-surface-gray-1 px-2 py-0.5 rounded-full">{{ t.name }}</span>
        </div>
        <div v-if="!templates.loading && !templates.data?.length" class="col-span-full flex items-center justify-center py-12">
          <div class="flex flex-col items-center gap-2"><ClipboardList class="size-12 text-ink-gray-4" /><div class="text-lg-medium text-ink-gray-6">No templates yet</div></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { createResource } from "frappe-ui";
import { __ } from "@/translation";
import LayoutHeader from "@/components/LayoutHeader.vue";
import Plus from "~icons/lucide/plus";
import LucideX from "~icons/lucide/x";
import LucidePlus from "~icons/lucide/plus";
import ClipboardList from "~icons/lucide/clipboard-list";

const showForm = ref(false);

const templates = createResource({ url: "helpdesk.tasky.api.get_templates", auto: true, transform: (d: any) => d ?? [] });

const form = reactive<{ template_name: string; industry: string; description: string; tasks: any[] }>({
  template_name: "", industry: "", description: "", tasks: [],
});

function addTaskRow() {
  form.tasks.push({ task_name: "", phase_name: "", category: "Functional", default_priority: "Medium", estimated_hours: 0 });
}

const save = createResource({
  url: "helpdesk.tasky.api.create_template",
  onSuccess() {
    form.template_name = ""; form.industry = ""; form.description = ""; form.tasks = [];
    showForm.value = false;
    templates.reload();
  },
});

function onSave() {
  save.submit({
    template_name: form.template_name,
    industry: form.industry,
    description: form.description,
    tasks: form.tasks.filter((t) => t.task_name),
  });
}
</script>
