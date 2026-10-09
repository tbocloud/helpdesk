<template>
  <Dialog
    :open="open"
    :title="editing ? __('Edit recurring task') : __('New recurring task')"
    size="2xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <TaskyState
      v-if="options.error"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the form')"
      :message="
        errorText(options.error, __('Check your connection, then try again.'))
      "
    >
      <Button :label="__('Try again')" @click="options.reload()" />
    </TaskyState>

    <div
      v-else-if="!options.data"
      class="flex flex-col gap-4"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div v-for="i in 4" :key="i" class="flex flex-col gap-1.5">
        <div class="h-3 w-24 animate-pulse rounded bg-surface-gray-2" />
        <div class="h-8 w-full animate-pulse rounded bg-surface-gray-1" />
      </div>
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-6"
      novalidate
      @submit.prevent="submit"
    >
      <section class="flex flex-col gap-4" :aria-labelledby="`${formId}-task`">
        <h3 :id="`${formId}-task`" class="text-base-medium text-ink-gray-9">
          {{ __("The task") }}
        </h3>
        <TextInput
          v-model="form.subject"
          :label="__('Task name')"
          :placeholder="__('e.g. Monthly backup check')"
          maxlength="140"
          required
        />
        <FormControl
          v-model="form.description"
          type="textarea"
          :rows="3"
          :label="__('Description')"
          :placeholder="__('Optional. What to check or deliver each time.')"
          :description="
            __(
              'Copied into every task. Left empty, the AI can write one when the task is created.'
            )
          "
        />
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
          <Combobox
            :label="__('Assignee')"
            :options="assigneeOptions"
            :placeholder="__('Unassigned')"
            :model-value="form.assignee || UNASSIGNED"
            @update:model-value="
              (v: string | null) =>
                (form.assignee = v && v !== UNASSIGNED ? v : null)
            "
          />
          <FormControl
            v-model="form.category"
            type="select"
            :label="__('Category')"
            :options="categoryOptions"
          />
          <FormControl
            v-model="form.priority"
            type="select"
            :label="__('Priority')"
            :options="priorityOptions"
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
        <FormControl
          v-model="form.is_key"
          type="checkbox"
          :label="__('Key task')"
          :description="
            __('Key tasks are highlighted in My Work and the overview')
          "
        />
      </section>

      <section
        class="flex flex-col gap-4"
        :aria-labelledby="`${formId}-schedule`"
      >
        <h3 :id="`${formId}-schedule`" class="text-base-medium text-ink-gray-9">
          {{ __("When it repeats") }}
        </h3>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.frequency"
            type="select"
            :label="__('Repeat')"
            :options="frequencyOptions"
          />
          <FormControl
            v-model.number="form.interval"
            type="number"
            min="1"
            max="99"
            :label="__('Every')"
            :description="everyLabel"
          />
        </div>

        <fieldset
          v-if="form.frequency === 'Weekly'"
          class="flex flex-col gap-1.5"
        >
          <legend class="mb-1.5 text-xs text-ink-gray-5">
            {{ __("On") }}
          </legend>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="day in WEEKDAYS"
              :key="day"
              type="button"
              class="flex h-11 min-w-11 items-center justify-center rounded-md border px-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 md:h-8 md:min-w-12"
              :class="
                form.weekdays.includes(day)
                  ? 'border-brand bg-brand-soft text-brand-ink'
                  : 'border-outline-gray-2 bg-surface-base text-ink-gray-7 hover:border-outline-gray-4'
              "
              :aria-pressed="form.weekdays.includes(day)"
              :aria-label="__(day)"
              @click="toggleWeekday(day)"
            >
              {{ __(day).slice(0, 3) }}
            </button>
          </div>
        </fieldset>

        <div
          v-if="usesDayOfMonth(form.frequency)"
          class="grid grid-cols-1 gap-4 sm:grid-cols-2"
        >
          <FormControl
            :model-value="
              form.last_day_of_month ? LAST_DAY : String(form.month_day ?? '')
            "
            type="select"
            :label="__('Day of the month')"
            :options="dayOptions"
            :description="
              form.last_day_of_month
                ? ''
                : __('The 29th to 31st fall on the last day of shorter months.')
            "
            @update:model-value="setDay"
          />
          <p
            v-if="form.frequency !== 'Monthly'"
            class="self-end text-p-xs text-ink-gray-5"
          >
            {{
              form.frequency === "Yearly"
                ? __("Repeats in the start date's month ({0}).", startMonth)
                : __(
                    "Counts quarters from the start date's month ({0}).",
                    startMonth
                  )
            }}
          </p>
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextInput
            v-model="form.start_date"
            type="date"
            :label="__('Starts on')"
            required
          />
          <FormControl
            v-model="form.ends"
            type="select"
            :label="__('Ends')"
            :options="endOptions"
          />
          <TextInput
            v-if="form.ends === 'On date'"
            v-model="form.end_date"
            type="date"
            :label="__('Last date')"
            :min="form.start_date"
          />
          <TextInput
            v-if="form.ends === 'After'"
            v-model.number="form.max_occurrences"
            type="number"
            min="1"
            :label="__('Number of tasks')"
          />
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextInput
            v-model.number="form.lead_days"
            type="number"
            min="0"
            max="365"
            :label="__('Create it this many days before it\'s due')"
            placeholder="0"
          />
          <TextInput
            :model-value="form.due_time ?? ''"
            type="time"
            :label="__('Due time (optional)')"
            @update:model-value="(v: string) => (form.due_time = v || null)"
          />
        </div>

        <FormControl
          v-model="form.skip_non_working_days"
          type="checkbox"
          :label="__('Move due dates off non-working days')"
          :description="
            form.frequency === 'Daily'
              ? __(
                  'Daily schedules leave out the weekly off, Saturdays off and holidays.'
                )
              : __(
                  'A date on the weekly off, a Saturday off or a holiday moves to the next working day.'
                )
          "
        />
      </section>

      <section
        class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
        :aria-labelledby="`${formId}-preview`"
        aria-live="polite"
      >
        <div class="flex items-center gap-2">
          <LucideCalendarClock
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <h3
            :id="`${formId}-preview`"
            class="text-sm font-medium text-ink-gray-8"
          >
            {{ __("Next due dates") }}
          </h3>
        </div>
        <p
          v-if="preview.data?.error"
          class="flex items-start gap-1.5 text-p-sm text-warning"
        >
          <LucideTriangleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>{{ preview.data.error }}</span>
        </p>
        <p v-else-if="preview.error" class="text-p-sm text-ink-gray-6">
          {{
            errorText(
              preview.error,
              __("Couldn't work out the dates right now.")
            )
          }}
        </p>
        <div
          v-else-if="!preview.data"
          class="flex flex-col gap-2"
          aria-busy="true"
        >
          <div
            v-for="i in 3"
            :key="i"
            class="h-3.5 w-2/3 animate-pulse rounded bg-surface-gray-2"
          />
        </div>
        <template v-else>
          <p class="text-p-sm text-ink-gray-7">{{ preview.data.schedule }}</p>
          <ol class="flex flex-col divide-y divide-outline-gray-1 text-sm">
            <li
              v-for="d in preview.data.dates"
              :key="d.on"
              class="flex items-center justify-between gap-3 py-1.5"
            >
              <span class="tabular-nums text-ink-gray-8">{{
                dateFormat(d.due, "ddd, D MMM YYYY")
              }}</span>
              <span
                v-if="d.create_on !== d.due"
                class="text-xs tabular-nums text-ink-gray-5"
                >{{
                  __("created {0}", dateFormat(d.create_on, "ddd, D MMM"))
                }}</span
              >
            </li>
          </ol>
        </template>
      </section>

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
          v-if="options.data"
          variant="solid"
          type="submit"
          :form="formId"
          :label="editing ? __('Save changes') : __('Create recurring task')"
          :loading="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import { watchDebounced } from "@vueuse/core";
import {
  Button,
  Combobox,
  Dialog,
  FormControl,
  TextInput,
  call,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import {
  FREQUENCY_UNIT,
  WEEKDAYS,
  usesDayOfMonth,
  type RecurringRule,
  type RecurringValues,
} from "../recurringMeta";

interface FormOptions {
  team: { user: string; full_name: string }[];
  categories: string[];
  priorities: string[];
  frequencies: string[];
  ends: string[];
  prefill: Partial<RecurringValues> | null;
}

const props = defineProps<{
  open: boolean;
  projectId: string;
  /** The schedule being edited; without it the dialog creates one. */
  rule?: RecurringRule | null;
  /** "Make recurring…" on a task: start from that task's values. */
  fromTask?: string | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [rule: RecurringRule];
}>();

const formId = `recurring-form-${useId()}`;
const UNASSIGNED = "__unassigned__";
const LAST_DAY = "last";
const editing = computed(() => !!props.rule);
const errorMessage = ref("");
const saving = ref(false);

function defaults(): RecurringValues {
  const today = dayjs();
  return {
    subject: "",
    description: "",
    category: "",
    priority: "Medium",
    estimated_hours: 0,
    assignee: null,
    is_key: false,
    frequency: "Monthly",
    interval: 1,
    // dayjs counts from Sunday, WEEKDAYS from Monday
    weekdays: [WEEKDAYS[(today.day() + 6) % 7]],
    month_day: today.date(),
    last_day_of_month: false,
    start_date: today.format("YYYY-MM-DD"),
    ends: "Never",
    end_date: null,
    max_occurrences: null,
    lead_days: 0,
    due_time: null,
    skip_non_working_days: true,
  };
}

const form = reactive<RecurringValues>(defaults());

function fill(values: Partial<RecurringValues>) {
  const base = defaults();
  Object.assign(form, base);
  for (const key of Object.keys(base) as (keyof RecurringValues)[]) {
    if (values[key] !== undefined)
      (form as Record<string, unknown>)[key] = values[key];
  }
  // a weekly rule always has days; a monthly one being switched to weekly may not
  if (!form.weekdays?.length) form.weekdays = base.weekdays;
  filled.value = JSON.stringify(form);
}

// what the form held when last filled: anything else is the person's own edits
const filled = ref("");
const edited = computed(() => JSON.stringify(form) !== filled.value);

function ruleValues(): Partial<RecurringValues> {
  return props.rule
    ? { ...props.rule, weekdays: [...props.rule.weekdays] }
    : {};
}

// the server works the dates out, so the preview and the daily job never disagree
const preview = createResource({
  url: "helpdesk.api.recurring_tasks.preview_recurring_task",
  onError() {},
});

const options = createResource({
  url: "helpdesk.api.recurring_tasks.get_recurring_task_form",
  makeParams: () => ({
    project: props.projectId,
    task: props.rule ? null : props.fromTask || null,
  }),
  onSuccess(data: FormOptions) {
    // only for the task still being made recurring, and never over the person's edits
    const forTask = options.params?.task ?? null;
    if (
      !props.rule &&
      data.prefill &&
      forTask === (props.fromTask || null) &&
      !edited.value
    )
      fill(data.prefill);
  },
});

// what the dialog is for: a new schedule, a task to make recurring, or a rule to edit
const source = computed(() =>
  JSON.stringify([
    props.projectId,
    props.rule?.name ?? null,
    props.fromTask ?? null,
  ])
);

watch(
  [() => props.open, source],
  ([open], previous) => {
    if (!open) return;
    const [wasOpen, previousSource] = previous ?? [false, ""];
    // reopened, or switched to another rule or task while open: start over
    if (!wasOpen || source.value !== previousSource) {
      errorMessage.value = "";
      preview.reset();
      fill(ruleValues());
      options.reload();
    }
  },
  { immediate: true }
);

// the rule reloaded while open (e.g. the list refreshed): take it, unless edited
watch(
  () => props.rule,
  (rule, previous) => {
    if (
      props.open &&
      rule &&
      previous &&
      rule.name === previous.name &&
      !edited.value
    )
      fill(ruleValues());
  }
);

const data = computed(() => options.data as FormOptions | undefined);

const assigneeOptions = computed(() => [
  { label: __("Unassigned"), value: UNASSIGNED },
  ...(data.value?.team ?? []).map((m) => ({
    label: m.full_name || m.user,
    value: m.user,
    description: m.user,
  })),
]);

const categoryOptions = computed(() => [
  { label: __("No category"), value: "" },
  ...(data.value?.categories ?? []).map((c) => ({ label: __(c), value: c })),
]);

const priorityOptions = computed(() =>
  (data.value?.priorities ?? []).map((p) => ({ label: __(p), value: p }))
);

const frequencyOptions = computed(() =>
  (data.value?.frequencies ?? []).map((f) => ({ label: __(f), value: f }))
);

const END_LABELS: Record<string, string> = {
  Never: "Never",
  "On date": "On a date",
  After: "After a number of tasks",
};
const endOptions = computed(() =>
  (data.value?.ends ?? []).map((e) => ({
    label: __(END_LABELS[e] ?? e),
    value: e,
  }))
);

const everyLabel = computed(() => {
  const [one, many] = FREQUENCY_UNIT[form.frequency] ?? ["", ""];
  const n = Number(form.interval) || 1;
  return n === 1
    ? __("Every {0}", __(one))
    : __("Every {0} {1}", String(n), __(many));
});

const dayOptions = computed(() => [
  ...Array.from({ length: 31 }, (_, i) => ({
    label: String(i + 1),
    value: String(i + 1),
  })),
  { label: __("Last day of the month"), value: LAST_DAY },
]);

const startMonth = computed(() =>
  form.start_date ? dayjs(form.start_date).format("MMMM") : ""
);

function setDay(value: string) {
  form.last_day_of_month = value === LAST_DAY;
  form.month_day = value === LAST_DAY ? null : Number(value);
}

function toggleWeekday(day: string) {
  const days = new Set(form.weekdays);
  if (days.has(day)) {
    // a weekly schedule needs at least one day
    if (days.size > 1) days.delete(day);
  } else {
    days.add(day);
  }
  form.weekdays = WEEKDAYS.filter((d) => days.has(d));
}

function values(): RecurringValues {
  return {
    ...form,
    subject: form.subject.trim(),
    interval: Number(form.interval) || 1,
    estimated_hours: Number(form.estimated_hours) || 0,
    lead_days: Number(form.lead_days) || 0,
    max_occurrences:
      form.ends === "After" ? Number(form.max_occurrences) || 0 : null,
    end_date: form.ends === "On date" ? form.end_date || null : null,
  };
}

const scheduleKey = computed(() =>
  JSON.stringify([
    form.frequency,
    form.interval,
    form.weekdays,
    form.month_day,
    form.last_day_of_month,
    form.start_date,
    form.ends,
    form.end_date,
    form.max_occurrences,
    form.lead_days,
    form.due_time,
    form.skip_non_working_days,
  ])
);

watchDebounced(
  [scheduleKey, () => props.open, () => !!options.data],
  ([, open, loaded]) => {
    if (open && loaded)
      preview.submit({
        project: props.projectId,
        name: props.rule?.name ?? null,
        values: values(),
      });
  },
  { debounce: 300, immediate: true }
);

async function submit() {
  if (saving.value) return;
  if (!form.subject.trim()) {
    errorMessage.value = __("Give the task a name.");
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  try {
    const saved: RecurringRule = await call(
      "helpdesk.api.recurring_tasks.save_recurring_task",
      {
        project: props.projectId,
        name: props.rule?.name ?? null,
        values: values(),
      }
    );
    toast.success(
      editing.value
        ? __("Recurring task saved")
        : __(
            "Recurring task created. Its next task is due {0}.",
            saved.next_due_date
              ? dateFormat(saved.next_due_date, "D MMM YYYY")
              : "—"
          )
    );
    emit("update:open", false);
    emit("saved", saved);
  } catch (e) {
    errorMessage.value = errorText(e, __("Couldn't save the recurring task."));
  } finally {
    saving.value = false;
  }
}
</script>
