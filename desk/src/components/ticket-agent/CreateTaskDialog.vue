<template>
  <!-- kept open on outside clicks so a half-filled task isn't lost;
       Cancel and the close button still dismiss it -->
  <Dialog
    v-model:open="open"
    :title="__('Create task from ticket')"
    size="xl"
    :dismissible="false"
  >
    <div
      v-if="context.loading && !context.data"
      class="flex flex-col gap-3 py-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div
        v-for="i in 4"
        :key="i"
        class="h-8 animate-pulse rounded bg-surface-gray-2"
      />
    </div>

    <div
      v-else-if="context.error && !context.data"
      role="alert"
      class="flex flex-col items-start gap-3 py-2"
    >
      <div class="flex items-start gap-2 text-p-sm text-ink-gray-7">
        <LucideCircleAlert
          class="mt-0.5 size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <span>{{ contextError }}</span>
      </div>
      <Button :label="__('Retry')" @click="context.reload()" />
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <section
        v-if="linkedTasks.length"
        class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
        :aria-labelledby="`${formId}-linked`"
      >
        <h3
          :id="`${formId}-linked`"
          class="mb-2 flex items-center gap-1.5 text-sm-medium text-ink-gray-8"
        >
          <LucideLink class="size-3.5 text-ink-gray-5" aria-hidden="true" />
          {{ __("Already linked to this ticket") }}
        </h3>
        <ul role="list" class="flex flex-col gap-1.5">
          <li
            v-for="task in linkedTasks"
            :key="task.name"
            class="flex min-w-0 items-center gap-2 text-sm"
          >
            <span
              class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-5"
            >
              {{ task.name }}
            </span>
            <span class="min-w-0 flex-1 truncate text-ink-gray-8">
              {{ task.subject }}
            </span>
            <TaskStatusBadge :status="task.status" />
          </li>
        </ul>
      </section>

      <FormControl
        v-model="form.project"
        type="select"
        :label="__('Project')"
        :options="projectOptions"
        :disabled="!projects.length"
        :description="
          projects.length
            ? undefined
            : __(
                'There are no open projects for this customer that you can add tasks to.'
              )
        "
        required
      />

      <TextInput
        v-model="form.task_name"
        :label="__('Task name')"
        :placeholder="__('What needs to be done?')"
        required
      />

      <Textarea
        v-model="form.description"
        :label="__('Description')"
        :placeholder="__('Optional details for whoever picks this up…')"
        :rows="3"
      />

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.assigned_to"
          type="select"
          :label="__('Assignee')"
          :options="assigneeOptions"
          :disabled="!form.project || !membersLoaded || !members.length"
          :description="
            form.project && membersLoaded && !members.length
              ? __(
                  'This project has no members yet, so the task stays unassigned'
                )
              : undefined
          "
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

      <p class="text-p-xs text-ink-gray-5">
        {{
          __(
            "The ticket will be set to Waiting on Task until this task is completed."
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
          :label="__('Create task')"
          :loading="createTask.loading"
          :disabled="!canSubmit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskStatusBadge from "@/pages/tasky/components/TaskStatusBadge.vue";
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
import LucideLink from "~icons/lucide/link";

interface ContextProject {
  name: string;
  project_name?: string;
  customer?: string | null;
}

interface LinkedTask {
  name: string;
  subject: string;
  status: string;
  project?: string;
  exp_end_date?: string | null;
}

interface TicketTaskContext {
  customer?: string | null;
  projects: ContextProject[];
  linked_tasks: LinkedTask[];
}

interface Member {
  user: string;
  full_name?: string;
}

const props = defineProps<{
  ticketId: string;
  ticketSubject?: string;
}>();

const emit = defineEmits<{
  created: [result: { task: Record<string, any>; ticket_status?: string }];
}>();

const open = defineModel<boolean>("open", { default: false });

const formId = `ticket-create-task-${useId()}`;

const form = reactive({
  project: "",
  task_name: "",
  description: "",
  assigned_to: "",
  due_date: "",
  is_key: false,
});

function errorText(err: any, fallback: string) {
  if (!err) return "";
  return err.messages?.length
    ? err.messages.join(" ")
    : err.message || fallback;
}

const context = createResource({
  url: "helpdesk.api.work.get_ticket_task_context",
  makeParams: () => ({ ticket: props.ticketId }),
  onSuccess(data: TicketTaskContext) {
    // the server lists the ticket customer's projects first
    if (!data.projects.some((p) => p.name === form.project)) {
      form.project = data.projects[0]?.name ?? "";
    }
  },
  onError() {},
});

const contextError = computed(() =>
  errorText(context.error, __("Couldn't load projects for this ticket."))
);

const projects = computed<ContextProject[]>(
  () => (context.data as TicketTaskContext | undefined)?.projects ?? []
);
const linkedTasks = computed<LinkedTask[]>(
  () => (context.data as TicketTaskContext | undefined)?.linked_tasks ?? []
);
const ticketCustomer = computed(
  () => (context.data as TicketTaskContext | undefined)?.customer
);

const projectOptions = computed(() => [
  ...(projects.value.length
    ? []
    : [{ label: __("No projects available"), value: "" }]),
  ...projects.value.map((p) => ({
    label:
      ticketCustomer.value && p.customer === ticketCustomer.value
        ? p.project_name || p.name
        : `${p.project_name || p.name}${p.customer ? ` (${p.customer})` : ""}`,
    value: p.name,
  })),
]);

const projectDetail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: form.project }),
  onError() {},
});

const members = computed<Member[]>(() =>
  form.project ? projectDetail.data?.users ?? [] : []
);
const membersLoaded = computed(
  () =>
    !projectDetail.loading && (!!projectDetail.data || !!projectDetail.error)
);

const assigneeOptions = computed(() => [
  {
    label:
      form.project && !membersLoaded.value
        ? __("Loading members…")
        : __("Unassigned"),
    value: "",
  },
  ...members.value.map((m) => ({
    label: m.full_name || m.user,
    value: m.user,
  })),
]);

watch(
  () => form.project,
  (project) => {
    form.assigned_to = "";
    projectDetail.reset();
    if (project) projectDetail.reload();
  }
);

const createTask = createResource({
  url: "helpdesk.api.work.create_task_from_ticket",
  onSuccess(data: { task: Record<string, any>; ticket_status?: string }) {
    toast.success(
      data?.ticket_status === "Waiting on Task"
        ? __("Task created — ticket is waiting on it")
        : __("Task created")
    );
    emit("created", data);
    open.value = false;
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  errorText(createTask.error, __("Couldn't create the task."))
);

const canSubmit = computed(
  () => !!form.project && !!form.task_name.trim() && !createTask.loading
);

function resetForm() {
  form.project = "";
  form.task_name = props.ticketSubject ?? "";
  form.description = "";
  form.assigned_to = "";
  form.due_date = "";
  form.is_key = false;
}

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    resetForm();
    createTask.reset();
    context.reload();
  },
  { immediate: true }
);

function submit() {
  if (!canSubmit.value) return;
  createTask.submit({
    ticket: props.ticketId,
    project: form.project,
    task_name: form.task_name.trim(),
    description: form.description,
    assigned_to: form.assigned_to,
    due_date: form.due_date || null,
    is_key: form.is_key,
  });
}
</script>
