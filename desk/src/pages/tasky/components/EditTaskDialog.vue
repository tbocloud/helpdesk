<template>
  <Dialog
    :open="!!props.task"
    :title="__('Edit task')"
    :message="canManage ? undefined : task?.subject"
    size="xl"
    @update:open="onOpenChange"
  >
    <div
      v-if="!loaded && !loadError"
      class="flex flex-col gap-3 py-2"
      aria-busy="true"
    >
      <div
        v-for="i in 4"
        :key="i"
        class="h-8 animate-pulse rounded bg-surface-gray-2"
      />
    </div>

    <div
      v-else-if="loadError"
      role="alert"
      class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{{ loadError }}</span>
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <template v-if="canManage">
        <TextInput
          v-model="form.task_name"
          :label="__('Task name')"
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
              :loading="assignable.loading"
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
            :options="categorySelectOptions"
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
        </div>

        <div
          v-if="!closed"
          class="flex flex-wrap items-center gap-x-2 gap-y-1 text-p-sm text-ink-gray-6"
        >
          <LucideCalendarClock
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span>{{
            __("Due date, key, milestone and dependency are under Plan.")
          }}</span>
          <button
            type="button"
            class="rounded text-ink-gray-8 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            @click="openPlan"
          >
            {{ __("Change dates & dependencies…") }}
          </button>
        </div>
      </template>

      <template v-else>
        <dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div
            v-for="row in readOnlyRows"
            :key="row.label"
            class="min-w-0"
            :class="row.wide ? 'col-span-2' : ''"
          >
            <dt class="text-xs text-ink-gray-5">{{ row.label }}</dt>
            <dd class="mt-1 truncate text-ink-gray-8">{{ row.value }}</dd>
          </div>
        </dl>

        <TaskDescriptionField
          v-model="form.description"
          v-model:ai-text="aiText"
          :context="draftContext"
          :placeholder="__('Details, notes, links…')"
          :rows="4"
          autofocus
        />

        <p class="flex items-start gap-2 text-p-sm text-ink-gray-6">
          <LucideLock
            class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          {{ __("Only the project lead or manager can change the rest.") }}
        </p>
      </template>

      <TaskPullRequests :pull-requests="task?.pull_requests" />

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
          :label="__('Save')"
          :loading="updateTask.loading"
          :disabled="!canSubmit"
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
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";
import {
  categoryOptions,
  errorText,
  isAiDrafted,
  isClosed,
  priorityOptions,
} from "../taskMeta";
import TaskDescriptionField, {
  type DraftContext,
} from "./TaskDescriptionField.vue";
import TaskPullRequests from "./TaskPullRequests.vue";

interface EditableTask {
  name: string;
  subject?: string;
  project?: string | null;
  [key: string]: any;
}

interface Person {
  name: string;
  full_name?: string;
}

const props = defineProps<{
  /** The task to edit; the dialog is open while this is set. */
  task: EditableTask | null;
  /** Project of the task, when the task dict doesn't carry it. */
  projectId?: string;
  /** Existing phase names, offered as suggestions. */
  phases?: string[];
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  saved: [task: Record<string, any>];
  /** Open the Plan dialog for this task (dates, key, milestone, dependency). */
  plan: [task: Record<string, any>];
}>();

const formId = `tasky-edit-task-${useId()}`;

const form = reactive({
  task_name: "",
  description: "",
  phase: "",
  category: "",
  priority: "Medium",
  estimated_hours: 0 as number | string,
  assigned_to: "",
});
// the assignee the task had when the dialog opened; only a change is sent
const initialAssignee = ref("");
// the description while it's still the AI's text (from the server or "Write with AI")
const aiText = ref<string | null>(null);

const detail = createResource({
  url: "helpdesk.tasky.api.get_task_detail",
  onSuccess(data: Record<string, any>) {
    fillForm(data);
    const project = data.project || props.projectId;
    if (project && projectDetail.params?.project !== project)
      projectDetail.submit({ project });
  },
  onError() {},
});

// who may change what, and the team for the assignee picker
const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  onError() {},
});

// active agents with enabled accounts; deleted or disabled people never appear
const assignable = createResource({
  url: "helpdesk.tasky.api.get_users",
  onError() {},
});

// the loaded task; the dialog's open state follows props.task instead, since closing
// clears the prop while this copy stays loaded
const task = computed<Record<string, any> | null>(() => detail.data ?? null);
const project = computed(
  () => task.value?.project || props.task?.project || props.projectId || ""
);
const canManage = computed(
  () =>
    projectDetail.params?.project === project.value &&
    !!projectDetail.data?.can_manage
);
const closed = computed(() => !!task.value && isClosed(task.value));

const loaded = computed(
  () =>
    !!task.value &&
    (!project.value ||
      (!projectDetail.loading &&
        projectDetail.params?.project === project.value &&
        (!!projectDetail.data || !!projectDetail.error)))
);
const loadError = computed(() =>
  detail.error ? errorText(detail.error, __("Couldn't load this task.")) : ""
);

const members = computed<{ user: string; full_name?: string }[]>(
  () => projectDetail.data?.users ?? []
);
const memberIds = computed(() => new Set(members.value.map((m) => m.user)));
const assignableUsers = computed(() => (assignable.data ?? []) as Person[]);

const UNASSIGNED = "__unassigned__";

// team first; anyone else picked here joins the team as a Developer
const assigneeOptions = computed(() => {
  const toOption = (u: Person) => ({
    label: u.full_name || u.name,
    value: u.name,
    description: u.name,
  });
  const team = assignableUsers.value.filter((u) => memberIds.value.has(u.name));
  const others = assignableUsers.value.filter(
    (u) => !memberIds.value.has(u.name)
  );
  return [
    { label: __("Unassigned"), value: UNASSIGNED },
    ...(team.length
      ? [{ group: __("Project team"), options: team.map(toOption) }]
      : []),
    ...(others.length
      ? [{ group: __("Other agents"), options: others.map(toOption) }]
      : []),
  ];
});

const assigneeIsNew = computed(
  () =>
    !!form.assigned_to &&
    form.assigned_to !== initialAssignee.value &&
    !memberIds.value.has(form.assigned_to)
);

// tasks raised from tickets may have no category; keep that selectable
const categorySelectOptions = computed(() =>
  task.value?.category
    ? categoryOptions()
    : [{ label: __("No category"), value: "" }, ...categoryOptions()]
);

const phaseOptions = computed(() =>
  [...new Set((props.phases ?? []).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b)
  )
);

function personName(user?: string | null) {
  if (!user) return __("Unassigned");
  return (
    members.value.find((m) => m.user === user)?.full_name ||
    assignableUsers.value.find((u) => u.name === user)?.full_name ||
    user
  );
}

const readOnlyRows = computed(() => {
  const t = task.value;
  if (!t) return [];
  return [
    { label: __("Task name"), value: t.subject, wide: true },
    { label: __("Assignee"), value: personName(t.assigned_to) },
    { label: __("Priority"), value: __(t.priority || "Medium") },
    { label: __("Category"), value: t.category ? __(t.category) : "—" },
    { label: __("Phase"), value: t.phase || "—" },
    {
      label: __("Estimate"),
      value: t.estimated_hours ? __("{0} hrs", String(t.estimated_hours)) : "—",
    },
  ];
});

// the assignee can only change the description, so the AI sees the saved details
const draftContext = computed<DraftContext>(() => {
  const t: Record<string, any> = task.value ?? props.task ?? {};
  const editing = canManage.value;
  return {
    task: props.task?.name,
    task_name: editing ? form.task_name : t.subject || "",
    project: project.value,
    category: editing ? form.category : t.category,
    phase: (editing ? form.phase : t.phase || "").trim(),
    priority: editing ? form.priority : t.priority,
    estimated_hours:
      Number(editing ? form.estimated_hours : t.estimated_hours) || 0,
    assigned_to: editing ? form.assigned_to : t.assigned_to || "",
  };
});

const canSubmit = computed(
  () =>
    loaded.value &&
    !updateTask.loading &&
    (!canManage.value || !!form.task_name.trim())
);

const updateTask = createResource({
  url: "helpdesk.tasky.api.update_task",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Task updated"));
    emit("saved", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  updateTask.error
    ? errorText(updateTask.error, __("Couldn't save the task."))
    : ""
);

function fillForm(t: Record<string, any>) {
  form.task_name = t.subject || "";
  form.description = t.description || "";
  form.phase = t.phase || "";
  form.category = t.category || "";
  form.priority = t.priority || "Medium";
  form.estimated_hours = t.estimated_hours || 0;
  form.assigned_to = t.assigned_to || "";
  initialAssignee.value = t.assigned_to || "";
  aiText.value = t.ai_description ? t.description || "" : null;
}

watch(
  () => props.task?.name,
  (name) => {
    if (!name || !props.task) return;
    detail.reset();
    updateTask.reset();
    fillForm(props.task);
    detail.submit({ task: name });
    const known = props.task.project || props.projectId;
    if (known && projectDetail.params?.project !== known)
      projectDetail.submit({ project: known });
    if (!assignable.data) assignable.reload();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function openPlan() {
  const t = task.value;
  if (!t) return;
  emit("update:task", null);
  emit("plan", t);
}

function submit() {
  if (!props.task || !canSubmit.value) return;
  if (!canManage.value) {
    updateTask.submit({
      task: props.task.name,
      description: form.description,
      ai_description: isAiDrafted(form.description, aiText.value),
    });
    return;
  }
  updateTask.submit({
    task: props.task.name,
    task_name: form.task_name.trim(),
    description: form.description,
    ai_description: isAiDrafted(form.description, aiText.value),
    phase: form.phase.trim(),
    category: form.category,
    priority: form.priority,
    estimated_hours: Number(form.estimated_hours) || 0,
    ...(form.assigned_to !== initialAssignee.value
      ? { assigned_to: form.assigned_to }
      : {}),
  });
}
</script>
