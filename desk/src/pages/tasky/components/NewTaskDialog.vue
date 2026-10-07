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

      <TaskDescriptionField
        v-model="form.description"
        v-model:ai-text="aiText"
        :context="draftContext"
        :placeholder="__('Optional details, acceptance criteria, links…')"
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

        <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
        <div class="flex flex-col gap-1.5">
          <Combobox
            :label="__('Assignee')"
            :options="assigneeOptions"
            :placeholder="__('Unassigned')"
            :loading="!membersLoaded || assignable.loading"
            :model-value="form.assigned_to || UNASSIGNED"
            @update:model-value="
              (v: string | null) =>
                (form.assigned_to = v && v !== UNASSIGNED ? v : '')
            "
          />
          <p v-if="assigneeIsNew" class="text-p-xs text-ink-gray-5">
            {{ __("They'll be added to the project as a Developer.") }}
          </p>
        </div>

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
        v-model="form.depends_on_task"
        type="select"
        :label="__('Depends on')"
        :options="dependencyOptions"
        :disabled="!openTasks.data && !openTasks.error"
        :description="
          __(
            'Optional. The task can\'t start or finish until this one is done.'
          )
        "
      />

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.is_key"
          type="checkbox"
          :label="__('Key task')"
          :description="
            __('Key tasks are highlighted in My Work and the overview')
          "
        />
        <FormControl
          v-model="form.is_milestone"
          type="checkbox"
          :label="__('Milestone')"
          :description="
            __('Milestones are listed on the project dashboard by due date')
          "
        />
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
  Combobox,
  Dialog,
  FormControl,
  TextInput,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { categoryOptions, isAiDrafted, priorityOptions } from "../taskMeta";
import TaskDescriptionField, {
  type DraftContext,
} from "./TaskDescriptionField.vue";

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
  is_milestone: false,
  depends_on_task: "",
});

// what the AI wrote into the description, so an unedited draft is saved as AI drafted
const aiText = ref<string | null>(null);

const draftContext = computed<DraftContext>(() => ({
  task_name: form.task_name,
  project: props.projectId,
  category: form.category,
  phase: form.phase.trim(),
  priority: form.priority,
  estimated_hours: Number(form.estimated_hours) || 0,
  assigned_to: form.assigned_to,
}));

function resetForm() {
  form.task_name = "";
  form.description = "";
  aiText.value = null;
  form.phase = props.defaultPhase ?? "";
  form.category = "Functional";
  form.priority = "Medium";
  form.estimated_hours = 0;
  form.due_date = "";
  form.assigned_to = "";
  form.is_key = false;
  form.is_milestone = false;
  form.depends_on_task = "";
}

const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: props.projectId }),
});

const openTasks = createResource({
  url: "helpdesk.tasky.api.get_project_tasks",
  makeParams: () => ({ project: props.projectId }),
  onError() {},
});

const dependencyOptions = computed(() => [
  {
    label: openTasks.data ? __("No dependency") : __("Loading tasks…"),
    value: "",
  },
  ...((openTasks.data ?? []) as { name: string; subject: string }[]).map(
    (t) => ({ label: t.subject, value: t.name })
  ),
]);

const members = computed<Member[]>(() => projectDetail.data?.users ?? []);
const membersLoaded = computed(
  () => !!projectDetail.data || !!projectDetail.error
);

// active agents with enabled accounts; deleted or disabled people never appear
const assignable = createResource({
  url: "helpdesk.tasky.api.get_users",
});

const assignableUsers = computed(
  () => (assignable.data ?? []) as { name: string; full_name?: string }[]
);

const memberIds = computed(() => new Set(members.value.map((m) => m.user)));

const UNASSIGNED = "__unassigned__";

// team first; anyone else picked here joins the team as a Developer
const assigneeOptions = computed(() => {
  const toOption = (u: { name: string; full_name?: string }) => ({
    label: u.full_name || u.name,
    value: u.name,
    description: u.name,
  });
  const team = assignableUsers.value.filter((u) => memberIds.value.has(u.name));
  const others = assignableUsers.value.filter(
    (u) => !memberIds.value.has(u.name)
  );
  // only the project's manager or lead brings new people onto the team
  const canBringIn = !!projectDetail.data?.can_manage;
  return [
    { label: __("Unassigned"), value: UNASSIGNED },
    ...(team.length
      ? [{ group: __("Project team"), options: team.map(toOption) }]
      : []),
    ...(others.length && canBringIn
      ? [{ group: __("Other agents"), options: others.map(toOption) }]
      : []),
  ];
});

const assigneeIsNew = computed(
  () => !!form.assigned_to && !memberIds.value.has(form.assigned_to)
);

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
    if (props.projectId) {
      projectDetail.reload();
      openTasks.reload();
    }
    assignable.reload();
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
    is_milestone: form.is_milestone,
    depends_on_task: form.depends_on_task || null,
    ai_description: isAiDrafted(form.description, aiText.value),
  });
}
</script>
