<template>
  <Dialog
    :open="open"
    :title="__('New task')"
    size="xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <TextInput
        v-model="form.task_name"
        :label="__('Task name')"
        :placeholder="__('e.g. Configure chart of accounts')"
        required
        autofocus
      />

      <Textarea
        v-model="form.description"
        :label="__('Description')"
        :placeholder="__('Optional details, acceptance criteria, links…')"
        :rows="3"
      />

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.phase"
          :label="__('Phase')"
          :placeholder="__('e.g. Discovery')"
          :list="phaseOptions.length ? `${formId}-phases` : undefined"
          autocomplete="off"
        />
        <datalist v-if="phaseOptions.length" :id="`${formId}-phases`">
          <option v-for="p in phaseOptions" :key="p" :value="p" />
        </datalist>

        <FormControl
          v-model="form.assigned_to"
          type="select"
          :label="__('Assignee')"
          :options="assigneeOptions"
          :disabled="!membersLoaded || !members.length"
          :description="
            membersLoaded && !members.length
              ? __('Add team members to the project to assign tasks')
              : undefined
          "
        />

        <FormControl
          v-model="form.category"
          type="select"
          :label="__('Category')"
          :options="categoryOptions()"
        />

        <FormControl
          v-model="form.priority"
          type="select"
          :label="__('Priority')"
          :options="priorityOptions()"
        />

        <TextInput
          v-model.number="form.estimated_hours"
          type="number"
          min="0"
          step="0.25"
          :label="__('Estimated hours')"
          placeholder="0"
        />

        <TextInput
          v-model="form.due_date"
          type="date"
          :label="__('Due date')"
        />
      </div>

      <FormControl
        v-model="form.is_key"
        type="checkbox"
        :label="__('Key task')"
        :description="
          __('Key tasks are highlighted in My Work and the overview')
        "
      />

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
          :label="__('Create task')"
          :loading="addTask.loading"
          :disabled="!form.task_name.trim()"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  FormControl,
  TextInput,
  Textarea,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { categoryOptions, priorityOptions } from "../taskMeta";

interface Member {
  user: string;
  full_name?: string;
}

const props = defineProps<{
  open: boolean;
  projectId: string;
  /** Existing phase names, offered as suggestions. */
  phases?: string[];
  defaultPhase?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  created: [task: Record<string, any>];
}>();

const formId = `tasky-new-task-${useId()}`;

const form = reactive({
  task_name: "",
  description: "",
  phase: "",
  category: "Functional",
  priority: "Medium",
  estimated_hours: 0 as number | string,
  due_date: "",
  assigned_to: "",
  is_key: false,
});

function resetForm() {
  form.task_name = "";
  form.description = "";
  form.phase = props.defaultPhase ?? "";
  form.category = "Functional";
  form.priority = "Medium";
  form.estimated_hours = 0;
  form.due_date = "";
  form.assigned_to = "";
  form.is_key = false;
}

const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: props.projectId }),
});

const members = computed<Member[]>(() => projectDetail.data?.users ?? []);
const membersLoaded = computed(
  () => !!projectDetail.data || !!projectDetail.error
);

const assigneeOptions = computed(() => [
  {
    label: membersLoaded.value ? __("Unassigned") : __("Loading members…"),
    value: "",
  },
  ...members.value.map((m) => ({
    label: m.full_name || m.user,
    value: m.user,
  })),
]);

const phaseOptions = computed(() =>
  [...new Set((props.phases ?? []).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b)
  )
);

const addTask = createResource({
  url: "helpdesk.tasky.api.add_task",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Task created"));
    emit("created", data);
    emit("update:open", false);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() => {
  const err = addTask.error as { messages?: string[]; message?: string } | null;
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || __("Couldn't create the task.");
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    resetForm();
    addTask.reset();
    if (props.projectId) projectDetail.reload();
  },
  { immediate: true }
);

function submit() {
  if (!form.task_name.trim() || addTask.loading) return;
  addTask.submit({
    project: props.projectId,
    task_name: form.task_name.trim(),
    description: form.description,
    phase: form.phase.trim(),
    category: form.category,
    priority: form.priority,
    estimated_hours: Number(form.estimated_hours) || 0,
    assigned_to: form.assigned_to,
    due_date: form.due_date || null,
    is_key: form.is_key,
  });
}
</script>
