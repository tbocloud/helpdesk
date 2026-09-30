<template>
  <Dialog
    :open="!!task"
    :title="__('Complete task')"
    :message="task?.subject"
    size="md"
    @update:open="onOpenChange"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <TextInput
        v-model="hours"
        type="number"
        inputmode="decimal"
        step="0.25"
        min="0.25"
        :max="MAX_HOURS"
        required
        :label="__('Hours worked')"
        :placeholder="__('e.g. 2.5')"
        :error="shownHoursError"
        :description="
          prefilledHours
            ? __('Filled in from the timer: {0} h', String(prefilledHours))
            : undefined
        "
        @blur="hoursTouched = true"
      />
      <Textarea
        v-model="notes"
        required
        :label="__('Notes')"
        :placeholder="__('What was done?')"
        :rows="3"
        :error="shownNotesError"
        @blur="notesTouched = true"
      />

      <p class="flex items-start gap-2 text-p-sm text-ink-gray-6">
        <LucideTimer
          class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{ __("The hours and notes are saved to your timesheet.") }}
      </p>

      <div
        v-if="serverError"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ serverError }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Complete task')"
          :loading="completeTask.loading"
          :disabled="!isValid"
        >
          <template #prefix>
            <LucideCircleCheck class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  TextInput,
  Textarea,
  createResource,
  dayjs,
  dayjsLocal,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideTimer from "~icons/lucide/timer";
import { PENDING_REVIEW, errorText } from "../taskMeta";

/** Same cap as MAX_HOURS_PER_COMPLETION in helpdesk/tasky/api.py. */
const MAX_HOURS = 24;

interface CompletableTask {
  name: string;
  subject?: string;
  custom_timer_start?: string | null;
  custom_timer_elapsed?: number | null;
}

interface CompleteResult {
  status: string;
  timesheet: string;
  timesheet_status: "Submitted" | "Draft";
  hours_logged: number;
}

const props = defineProps<{
  /** The task to complete; the dialog is open while this is set. */
  task: CompletableTask | null;
  /**
   * Hours the page's own timer shows for the task. Without it, the tracked
   * time is worked out from the task's timer fields.
   */
  trackedHours?: number | null;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  completed: [result: CompleteResult];
}>();

const formId = `tasky-complete-task-${useId()}`;
const hours = ref("");
const notes = ref("");
const prefilledHours = ref(0);
const hoursTouched = ref(false);
const notesTouched = ref(false);

const completeTask = createResource({
  url: "helpdesk.tasky.api.complete_task",
  onSuccess(data: CompleteResult) {
    announce(data);
    emit("completed", data);
    emit("update:task", null);
  },
  // shown inline so the hours and notes aren't lost
  onError() {},
});

const hoursValue = computed(() =>
  String(hours.value ?? "").trim() === "" ? NaN : Number(hours.value)
);

const hoursError = computed(() => {
  if (String(hours.value ?? "").trim() === "")
    return __("Enter the hours you worked on this task.");
  if (!(hoursValue.value > 0)) return __("Hours must be more than 0.");
  if (hoursValue.value > MAX_HOURS)
    return __(
      "You can log at most {0} hours here. Log longer work on a timesheet.",
      String(MAX_HOURS)
    );
  return "";
});
const notesError = computed(() =>
  notes.value.trim() ? "" : __("Add a note on what was done.")
);
const isValid = computed(() => !hoursError.value && !notesError.value);

// a wrong number is flagged as it's typed; an empty field once it's been left
const shownHoursError = computed(() =>
  hoursTouched.value || String(hours.value ?? "").trim() !== ""
    ? hoursError.value || undefined
    : undefined
);
const shownNotesError = computed(() =>
  notesTouched.value ? notesError.value || undefined : undefined
);

const serverError = computed(() =>
  completeTask.error
    ? errorText(completeTask.error, __("Couldn't complete the task."))
    : ""
);

watch(
  () => props.task?.name,
  (name) => {
    if (!name || !props.task) return;
    prefilledHours.value = roundToQuarter(
      props.trackedHours ?? timerHours(props.task)
    );
    hours.value = prefilledHours.value ? String(prefilledHours.value) : "";
    notes.value = "";
    hoursTouched.value = false;
    notesTouched.value = false;
    completeTask.reset();
  },
  { immediate: true }
);

/** Paused time plus the running stretch, in hours. */
function timerHours(task: CompletableTask) {
  let tracked = Number(task.custom_timer_elapsed) || 0;
  if (task.custom_timer_start) {
    // the start is stored in the server's time zone
    const running = dayjs().diff(dayjsLocal(task.custom_timer_start), "second");
    if (running > 0) tracked += running / 3600;
  }
  return tracked;
}

// nearest quarter hour, never 0 for time that was tracked, and within the cap
function roundToQuarter(value: number) {
  if (!(value > 0)) return 0;
  return Math.min(Math.max(Math.round(value * 4) / 4, 0.25), MAX_HOURS);
}

function announce(data: CompleteResult) {
  const logged = String(data.hours_logged);
  if (data.timesheet_status === "Draft") {
    toast.warning(
      __(
        "Task done · {0}h saved to timesheet {1} as a draft, as it couldn't be submitted.",
        logged,
        data.timesheet
      )
    );
  } else if (data.status === PENDING_REVIEW) {
    toast.info(
      __(
        "Sent to the project lead for review · {0}h logged to timesheet {1}",
        logged,
        data.timesheet
      )
    );
  } else {
    toast.success(
      __("Completed · {0}h logged to timesheet {1}", logged, data.timesheet)
    );
  }
}

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  hoursTouched.value = true;
  notesTouched.value = true;
  if (!props.task || !isValid.value || completeTask.loading) return;
  completeTask.submit({
    task: props.task.name,
    hours_worked: hoursValue.value,
    notes: notes.value.trim(),
  });
}
</script>
