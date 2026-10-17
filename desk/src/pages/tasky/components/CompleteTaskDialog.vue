<template>
  <Dialog
    :open="!!task"
    :title="forReview ? __('Send for review') : __('Complete task')"
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
      <!-- one row per day worked, filled in from the timer's sessions, so each day's
           hours land on that day in the timesheet -->
      <fieldset
        class="flex flex-col gap-2"
        :aria-describedby="shownHoursError ? hoursErrorId : undefined"
        :aria-invalid="shownHoursError ? true : undefined"
      >
        <legend class="mb-1.5 text-xs text-ink-gray-5">
          {{ __("Hours worked") }} <span class="text-danger">*</span>
        </legend>
        <div
          v-if="daysLoading && !rows.length"
          class="h-8 animate-pulse rounded bg-surface-gray-2"
          aria-hidden="true"
        />
        <div
          v-for="(row, index) in rows"
          :key="row.key"
          class="flex flex-col gap-1"
        >
          <div class="flex items-start gap-2">
            <TextInput
              v-model="row.date"
              type="date"
              class="min-w-0 flex-1"
              :max="today"
              :min="earliest"
              :aria-label="__('Day {0}', String(index + 1))"
            />
            <TextInput
              v-model="row.hours"
              type="number"
              inputmode="decimal"
              step="0.25"
              min="0.25"
              :max="MAX_HOURS"
              class="w-24 shrink-0"
              :placeholder="__('Hours')"
              :aria-label="__('Hours on day {0}', String(index + 1))"
            />
            <Button
              v-if="rows.length > 1"
              variant="ghost"
              :label="__('Remove this day')"
              :tooltip="__('Remove this day')"
              @click="rows.splice(index, 1)"
            >
              <template #icon>
                <LucideX class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <p
            v-if="row.long"
            class="flex items-start gap-1.5 text-p-xs text-warning"
          >
            <LucideTriangleAlert
              class="mt-0.5 size-3.5 shrink-0"
              aria-hidden="true"
            />
            {{
              __(
                "The timer ran over {0} hours this day. Was it left running? Check the hours.",
                String(LONG_DAY_HOURS)
              )
            }}
          </p>
          <p v-if="row.fromTimer" class="text-p-xs text-ink-gray-5">
            {{ __("From the timer: {0} h", String(row.fromTimer)) }}
          </p>
        </div>
        <div class="flex items-center justify-between gap-2">
          <Button
            variant="ghost"
            :label="__('Add another day')"
            @click="addRow()"
          >
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <span
            v-if="rows.length > 1"
            class="text-sm tabular-nums text-ink-gray-7"
          >
            {{ __("Total {0} h", String(totalHours)) }}
          </span>
        </div>
        <p
          v-if="shownHoursError"
          :id="hoursErrorId"
          class="text-p-xs text-danger"
          role="alert"
        >
          {{ shownHoursError }}
        </p>
      </fieldset>
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
        {{
          __(
            "The hours and notes are saved to your timesheet, one timesheet per day."
          )
        }}
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
          :label="forReview ? __('Send for review') : __('Complete task')"
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
import { errorText } from "@/utils";
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  TextInput,
  Textarea,
  call,
  createResource,
  dayjs,
  dayjsLocal,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucidePlus from "~icons/lucide/plus";
import LucideTimer from "~icons/lucide/timer";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import { PENDING_REVIEW } from "../taskMeta";

/** A day's cap: MAX_HOURS_PER_COMPLETION in helpdesk/tasky/api.py. */
const MAX_HOURS = 24;
/** LONG_DAY_HOURS in helpdesk/tasky/time_sessions.py. */
const LONG_DAY_HOURS = 10;

interface CompletableTask {
  name: string;
  subject?: string;
  creation?: string;
  custom_timer_start?: string | null;
  custom_timer_elapsed?: number | null;
}

interface CompleteResult {
  status: string;
  /** one per day worked */
  timesheets?: string[];
  timesheet: string;
  timesheet_status: "Submitted" | "Draft";
  /** the ones that couldn't be submitted and were kept as drafts */
  draft_timesheets?: string[];
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
  /** Send it to the lead for review even on a project that doesn't ask for one. */
  forReview?: boolean;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  completed: [result: CompleteResult];
}>();

interface DayRow {
  key: number;
  date: string;
  hours: string;
  /** what the timer recorded that day, shown beside the row */
  fromTimer?: number;
  long?: boolean;
}

interface CompletionDay {
  date: string;
  hours: number;
  long: boolean;
}

const formId = `tasky-complete-task-${useId()}`;
const rows = ref<DayRow[]>([]);
const notes = ref("");
const hoursTouched = ref(false);
const notesTouched = ref(false);
const hoursErrorId = `${formId}-hours-error`;
// the site's today, from the server when the days load (the browser's clock and time zone
// can differ from the site's); the browser's until then
const today = ref(dayjs().format("YYYY-MM-DD"));
const earliest = computed(() =>
  props.task?.creation
    ? dayjsLocal(props.task.creation).format("YYYY-MM-DD")
    : undefined
);
let nextKey = 0;

function addRow(date = "", hours = "", extra: Partial<DayRow> = {}) {
  rows.value.push({ key: nextKey++, date, hours, ...extra });
}

// the days the task's timer ran, from its saved sessions; only the latest request's answer
// counts, so a slow reply for a task closed a moment ago never fills another task's rows
const daysLoading = ref(false);
let daysRequest = 0;

async function loadDays(task: string) {
  const request = ++daysRequest;
  daysLoading.value = true;
  try {
    const data: { today: string; days: CompletionDay[] } = await call(
      "helpdesk.tasky.api.get_completion_days",
      { task }
    );
    if (request !== daysRequest || props.task?.name !== task) return;
    today.value = data.today || today.value;
    fillRows(data.days || []);
  } catch {
    // without the days, the timer's total goes on today, as before
    if (request === daysRequest && props.task?.name === task) fallbackRow();
  } finally {
    if (request === daysRequest) daysLoading.value = false;
  }
}

// each day to the nearest quarter hour; a few minutes on a day round to nothing and are
// left out, unless that leaves no time at all
function fillRows(data: CompletionDay[]) {
  rows.value = [];
  for (const d of data) {
    const hours = Math.min(Math.round(d.hours * 4) / 4, MAX_HOURS);
    if (hours > 0)
      addRow(d.date, String(hours), {
        fromTimer: Math.round(d.hours * 100) / 100,
        long: d.long,
      });
  }
  const tracked = data.reduce((n, d) => n + d.hours, 0);
  if (!rows.value.length && tracked > 0) {
    const last = data[data.length - 1];
    addRow(last.date, String(roundToQuarter(tracked)), {
      fromTimer: Math.round(tracked * 100) / 100,
    });
  }
  if (!rows.value.length) fallbackRow();
}

function fallbackRow() {
  if (!props.task) return;
  rows.value = [];
  const tracked = roundToQuarter(props.trackedHours ?? timerHours(props.task));
  addRow(today.value, tracked ? String(tracked) : "", {
    fromTimer: tracked || undefined,
  });
}

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

const rowHours = (row: DayRow) =>
  String(row.hours ?? "").trim() === "" ? NaN : Number(row.hours);

const totalHours = computed(
  () =>
    Math.round(
      rows.value.reduce((n, r) => n + (rowHours(r) > 0 ? rowHours(r) : 0), 0) *
        100
    ) / 100
);

const hoursError = computed(() => {
  if (!rows.value.length) return __("Enter the hours you worked on this task.");
  const seen = new Set<string>();
  for (const row of rows.value) {
    if (!row.date) return __("Pick the date for each day's hours.");
    if (row.date > today.value)
      return __(
        "{0} hasn't come yet; log hours only for days you worked.",
        row.date
      );
    if (earliest.value && row.date < earliest.value)
      return __("{0} is before this task was created.", row.date);
    if (seen.has(row.date))
      return __(
        "{0} is listed twice. Put that day's hours in one row.",
        row.date
      );
    seen.add(row.date);
    const h = rowHours(row);
    if (String(row.hours ?? "").trim() === "")
      return __("Enter the hours for each day, or remove the day.");
    if (!(h > 0)) return __("Hours must be more than 0.");
    if (h > MAX_HOURS)
      return __("A day has at most {0} hours.", String(MAX_HOURS));
  }
  return "";
});
const notesError = computed(() =>
  notes.value.trim() ? "" : __("Add a note on what was done.")
);
const isValid = computed(() => !hoursError.value && !notesError.value);

// the days' problems show once Complete is pressed, then follow the edits
const shownHoursError = computed(() =>
  hoursTouched.value ? hoursError.value || undefined : undefined
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
    rows.value = [];
    loadDays(name);
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
  const sheets = data.timesheets?.length ? data.timesheets : [data.timesheet];
  // one timesheet per day worked
  const where =
    sheets.length > 1
      ? __("{0} timesheets ({1})", String(sheets.length), sheets.join(", "))
      : __("timesheet {0}", sheets[0]);
  if (data.timesheet_status === "Draft") {
    const drafts = data.draft_timesheets?.length
      ? data.draft_timesheets
      : sheets;
    toast.warning(
      drafts.length === sheets.length
        ? __(
            "Task done · {0}h saved to {1} as a draft, as it couldn't be submitted.",
            logged,
            where
          )
        : __(
            "Task done · {0}h saved to {1}; {2} kept as a draft, as it couldn't be submitted.",
            logged,
            where,
            drafts.join(", ")
          )
    );
  } else if (data.status === PENDING_REVIEW) {
    toast.info(
      __(
        "Sent to the project lead for review · {0}h logged to {1}",
        logged,
        where
      )
    );
  } else {
    toast.success(__("Completed · {0}h logged to {1}", logged, where));
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
    days: rows.value.map((r) => ({ date: r.date, hours: rowHours(r) })),
    notes: notes.value.trim(),
    for_review: props.forReview,
  });
}
</script>
