<template>
  <Dialog
    :open="!!task"
    :title="__('Plan task')"
    :message="task?.subject"
    size="lg"
    @update:open="onOpenChange"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="flex flex-col gap-1.5">
        <TextInput
          v-model="form.due_date"
          type="date"
          :label="__('Due date')"
        />
        <p class="text-p-sm text-ink-gray-5">
          <template v-if="task?.due_date">
            {{ __("Currently due") }}
            <span class="font-mono tabular-nums text-ink-gray-7">{{
              formatDate(task.due_date)
            }}</span>
          </template>
          <template v-else>{{ __("No due date yet") }}</template>
        </p>
        <p
          v-if="slipCount > 0"
          class="flex items-center gap-1.5 text-p-sm text-warning"
        >
          <LucideCalendarClock class="size-3.5 shrink-0" aria-hidden="true" />
          <span class="tabular-nums">{{
            slipCount === 1
              ? __("Rescheduled 1 time so far")
              : __("Rescheduled {0} times so far", String(slipCount))
          }}</span>
        </p>
      </div>

      <Textarea
        v-if="movesLater"
        v-model="form.reason"
        :label="__('Why is it moving?')"
        :placeholder="__('e.g. Customer sent the data late')"
        :rows="2"
        required
      />

      <div class="flex flex-col gap-3">
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

      <FormControl
        v-model="form.depends_on_task"
        type="select"
        :label="__('Depends on')"
        :options="dependencyOptions"
        :disabled="!candidates.data && !candidates.error"
        :description="
          __('The task can\'t start or finish until this one is done.')
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
          :label="__('Save plan')"
          :loading="updatePlan.loading"
          :disabled="!canSubmit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  FormControl,
  TextInput,
  Textarea,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";

interface PlannableTask {
  name: string;
  subject?: string;
  project?: string | null;
  due_date?: string | null;
  is_key?: boolean;
  is_milestone?: boolean;
  slip_count?: number;
  depends_on_task?: string | null;
  depends_on_subject?: string | null;
}

const props = defineProps<{
  /** The task to plan; the dialog is open while this is set. */
  task: PlannableTask | null;
  /** Project of the task, when the task dict doesn't carry it. */
  projectId?: string;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  saved: [task: Record<string, any>];
}>();

const formId = `tasky-plan-task-${useId()}`;

const form = reactive({
  due_date: "",
  reason: "",
  is_key: false,
  is_milestone: false,
  depends_on_task: "",
});
const localError = ref("");

const project = computed(() => props.task?.project || props.projectId || "");
const slipCount = computed(() => props.task?.slip_count ?? 0);

const candidates = createResource({
  url: "helpdesk.tasky.api.get_project_tasks",
  makeParams: () => ({ project: project.value }),
  onError() {},
});

const dependencyOptions = computed(() => {
  const own = props.task?.name;
  const open = ((candidates.data ?? []) as { name: string; subject: string }[])
    .filter((t) => t.name !== own)
    .map((t) => ({ label: t.subject, value: t.name }));
  // a finished dependency drops out of the open list; keep it selectable so saving doesn't clear it
  const current = props.task?.depends_on_task;
  if (current && !open.some((o) => o.value === current)) {
    open.unshift({
      label: props.task?.depends_on_subject || current,
      value: current,
    });
  }
  return [
    {
      label: candidates.data ? __("No dependency") : __("Loading tasks…"),
      value: "",
    },
    ...open,
  ];
});

const dueChanged = computed(
  () => !!form.due_date && form.due_date !== (props.task?.due_date || "")
);
const movesLater = computed(
  () =>
    dueChanged.value &&
    !!props.task?.due_date &&
    dayjs(form.due_date).isAfter(dayjs(props.task.due_date), "day")
);
const canSubmit = computed(() => !movesLater.value || !!form.reason.trim());

const updatePlan = createResource({
  url: "helpdesk.tasky.api.update_task_plan",
  onSuccess(data: Record<string, any>) {
    toast.success(__("Plan updated"));
    emit("saved", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(
  () =>
    localError.value ||
    (updatePlan.error
      ? errorText(updatePlan.error, __("Couldn't save the plan."))
      : "")
);

watch(
  () => props.task?.name,
  (name) => {
    if (!name || !props.task) return;
    form.due_date = props.task.due_date || "";
    form.reason = "";
    form.is_key = !!props.task.is_key;
    form.is_milestone = !!props.task.is_milestone;
    form.depends_on_task = props.task.depends_on_task || "";
    localError.value = "";
    updatePlan.reset();
    if (project.value) candidates.reload();
  },
  { immediate: true }
);

function formatDate(date: string) {
  return dayjs(date).format("D MMM YYYY");
}

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || updatePlan.loading) return;
  localError.value = "";
  if (movesLater.value && !form.reason.trim()) {
    localError.value = __("Say why the due date is moving later.");
    return;
  }
  updatePlan.submit({
    task: props.task.name,
    due_date: dueChanged.value ? form.due_date : null,
    reason: movesLater.value ? form.reason.trim() : "",
    is_key: form.is_key,
    is_milestone: form.is_milestone,
    depends_on_task: form.depends_on_task || null,
    clear_dependency: !form.depends_on_task,
  });
}
</script>
