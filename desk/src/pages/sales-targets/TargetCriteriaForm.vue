<template>
  <!-- the list scrolls; the Assign button stays in view under it -->
  <form
    class="flex min-h-0 flex-1 flex-col"
    novalidate
    @submit.prevent="assign"
  >
    <div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
      <p
        v-if="replaceNote"
        class="flex items-start gap-2 rounded-lg bg-surface-gray-1 px-3 py-2.5 text-p-sm text-ink-gray-7"
      >
        <LucideInfo
          class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
          aria-hidden="true"
        />
        <span>{{ replaceNote }}</span>
      </p>

      <fieldset class="flex min-w-0 flex-col">
        <legend class="mb-2 text-sm font-semibold text-ink-gray-9 tabular-nums">
          {{ __("Targets for {0}", monthTitle(month)) }}
          <span v-if="criteria.length" class="font-normal text-ink-gray-6">
            · {{ criteria.length }}
          </span>
        </legend>
        <TaskyState
          v-if="!criteria.length"
          class="rounded-lg border border-dashed border-outline-gray-3 py-8"
          :icon="LucideListPlus"
          :title="__('No targets on the list')"
          :message="
            __('Add one below to give these people something to aim for.')
          "
        />
        <!-- one row a target: its name and kind on the left, the figure on the right -->
        <ol
          v-else
          class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
        >
          <li
            v-for="(row, index) in criteria"
            :key="row.key"
            class="grid grid-cols-[1.25rem_minmax(0,1fr)_8rem_2rem] items-center gap-x-2 gap-y-2 py-2.5 pl-3 pr-1.5"
          >
            <span
              class="text-xs font-medium text-ink-gray-5 tabular-nums"
              aria-hidden="true"
              >{{ index + 1 }}</span
            >
            <label :for="inputId(row)" class="flex min-w-0 flex-col">
              <span
                class="truncate text-sm font-medium text-ink-gray-8"
                :title="row.criterion"
                >{{ row.criterion }}</span
              >
            </label>
            <FormControl
              v-if="row.value_type !== 'Text'"
              :id="inputId(row)"
              v-model="row.target"
              type="number"
              size="md"
              min="0"
              :max="row.value_type === 'Percent' ? 100 : undefined"
              step="any"
              inputmode="decimal"
              class="[&_input]:text-right [&_input]:font-mono [&_input]:tabular-nums"
              :class="problems[row.key] && '[&_input]:!border-danger'"
              :placeholder="PLACEHOLDERS[row.value_type]"
              :aria-invalid="!!problems[row.key]"
              :aria-describedby="problems[row.key] ? problemId(row) : undefined"
            >
              <template v-if="row.value_type === 'Amount'" #prefix>
                <span class="text-sm text-ink-gray-6">{{ symbol }}</span>
              </template>
              <template v-else-if="row.value_type === 'Percent'" #suffix>
                <span class="text-sm text-ink-gray-6">%</span>
              </template>
            </FormControl>
            <span v-else aria-hidden="true" />
            <Button
              variant="ghost"
              :aria-label="__('Remove {0}', row.criterion)"
              @click="remove(row.key)"
            >
              <template #icon>
                <LucideX class="size-4 text-ink-gray-6" />
              </template>
            </Button>
            <FormControl
              v-if="row.value_type === 'Text'"
              :id="inputId(row)"
              v-model="row.target"
              type="textarea"
              :rows="2"
              class="col-span-2 col-start-2"
              :class="problems[row.key] && '[&_textarea]:!border-danger'"
              :placeholder="textPlaceholder(row)"
              :aria-invalid="!!problems[row.key]"
              :aria-describedby="problems[row.key] ? problemId(row) : undefined"
            />
            <p
              v-if="problems[row.key]"
              :id="problemId(row)"
              class="col-span-2 col-start-2 flex items-center gap-1 text-xs text-danger"
            >
              <LucideCircleAlert class="size-3.5 shrink-0" aria-hidden="true" />
              {{ problems[row.key] }}
            </p>
            <!-- what counts towards it, in words, so the head knows what they ask for -->
            <div
              v-if="row.value_type !== 'Text'"
              class="col-span-3 col-start-2 flex min-w-0 flex-col gap-1.5"
            >
              <div class="flex min-w-0 items-center gap-2">
                <label
                  :for="measureId(row)"
                  class="shrink-0 text-xs font-medium text-ink-gray-6"
                  >{{ __("Counts") }}</label
                >
                <FormControl
                  :id="measureId(row)"
                  v-model="row.measure"
                  type="select"
                  size="sm"
                  class="min-w-0 flex-1"
                  :options="measureOptions(row.value_type)"
                />
              </div>
              <TargetProgress
                v-if="rowResult(row)"
                class="mt-1"
                :criterion="row"
                :result="rowResult(row)!"
                :progress="progress!"
                :owner="savedFor!.full_name"
                :link="
                  auth.canUseLeads
                    ? leadsLink(row, progress!, savedFor!.user)
                    : null
                "
              />
            </div>
            <KpiStatus
              v-else-if="savedFor && isKpi(row) && row.kpi_status !== undefined"
              class="col-span-3 col-start-2"
              :criterion="row"
              :month="month"
              mode="head"
              :employee="savedFor.user"
              @changed="emit('assigned')"
            />
          </li>
        </ol>
      </fieldset>

      <!-- the head's own targets, beyond the five -->
      <div
        class="flex flex-col gap-2"
        role="group"
        :aria-labelledby="addHeading"
      >
        <h3 :id="addHeading" class="text-sm font-semibold text-ink-gray-9">
          {{ __("Add a target") }}
        </h3>
        <div class="grid grid-cols-[minmax(0,1fr)_7rem_auto] items-start gap-2">
          <FormControl
            v-model="newName"
            type="text"
            size="md"
            :placeholder="__('e.g. Demos given')"
            :aria-label="__('Name of the new target')"
            :aria-invalid="!!addProblem"
            :aria-describedby="addProblem ? addProblemId : undefined"
            @keydown.enter.prevent="add"
          />
          <FormControl
            v-model="newType"
            type="select"
            size="md"
            :aria-label="__('What kind of figure it is')"
            :options="typeOptions"
          />
          <Button
            size="md"
            :label="__('Add')"
            :disabled="criteria.length >= MAX_CRITERIA"
            @click="add"
          >
            <template #prefix>
              <LucidePlus class="size-4" />
            </template>
          </Button>
        </div>
        <p
          v-if="addProblem"
          :id="addProblemId"
          class="flex items-center gap-1 text-xs text-danger"
          role="alert"
        >
          <LucideCircleAlert class="size-3.5 shrink-0" aria-hidden="true" />
          {{ addProblem }}
        </p>
        <p
          v-else-if="criteria.length >= MAX_CRITERIA"
          class="text-xs text-ink-gray-6"
        >
          {{
            __("That's the most a month can have: {0}.", String(MAX_CRITERIA))
          }}
        </p>
      </div>
    </div>

    <div
      class="flex flex-col gap-2 rounded-b-xl border-t border-outline-gray-2 bg-surface-base p-4"
    >
      <ErrorMessage v-if="error" :message="error" role="alert" />
      <Button
        type="submit"
        variant="solid"
        size="md"
        class="w-full"
        :label="assignLabel"
        :loading="saving"
        :disabled="!criteria.length"
      >
        <template #prefix>
          <LucideUserCheck class="size-4" />
        </template>
      </Button>
    </div>
  </form>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, ErrorMessage, FormControl, toast } from "frappe-ui";
import { computed, nextTick, reactive, ref, useId } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideListPlus from "~icons/lucide/list-plus";
import LucidePlus from "~icons/lucide/plus";
import LucideUserCheck from "~icons/lucide/user-check";
import LucideX from "~icons/lucide/x";
import KpiStatus from "./KpiStatus.vue";
import TargetProgress from "./TargetProgress.vue";
import {
  currencySymbol,
  isKpi,
  leadsLink,
  MEASURE_LOOK,
  monthTitle,
  progressOf,
  VALUE_TYPE_LOOK,
  type Criterion,
  type Measure,
  type Progress,
  type TargetPerson,
  type ValueType,
} from "./salesTargets";

const props = defineProps<{
  month: string;
  currency: string;
  valueTypes: ValueType[];
  /** what the criteria start as: the one person's saved targets, else the defaults */
  start: Criterion[];
  people: TargetPerson[];
  /** the measures that fit each value type */
  measures: Record<ValueType, Measure[]>;
  /** the one person picked, when the form opened on their saved targets */
  savedFor: TargetPerson | null;
  /** their progress for the month, counted from their leads (null: none to show) */
  progress: Progress | null;
}>();
const emit = defineEmits<{ assigned: [] }>();

// the server keeps to as many (helpdesk.sales_targets.MAX_CRITERIA)
const MAX_CRITERIA = 30;
const PLACEHOLDERS: Record<ValueType, string> = {
  Amount: "500000",
  Number: "20",
  Percent: "90",
  Text: "",
};
// what an information-only target usually holds, by its name
const INFO_PLACEHOLDERS: Record<string, string> = {
  industry: __("e.g. Solar, Hospitality"),
  location: __("e.g. Ernakulam, Thrissur"),
};
function textPlaceholder(row: Row) {
  if (!row.info_only) return __("e.g. 3 case studies published");
  return INFO_PLACEHOLDERS[row.criterion.toLowerCase()] ?? "";
}

type Row = Criterion & { key: number };

const formId = useId();
const addHeading = useId();
const addProblemId = useId();
let nextKey = 0;
const criteria = ref<Row[]>(props.start.map((c) => ({ ...c, key: nextKey++ })));
const problems = reactive<Record<number, string>>({});
const symbol = computed(() => currencySymbol(props.currency));
const typeOptions = computed(() => [
  ...props.valueTypes.map((t) => ({
    label: VALUE_TYPE_LOOK[t].label,
    value: t,
  })),
  { label: __("Text, info only"), value: "Info" },
]);

const auth = useAuthStore();
const inputId = (row: Row) => `${formId}-target-${row.key}`;
const measureId = (row: Row) => `${formId}-measure-${row.key}`;

function measureOptions(type: ValueType) {
  return [
    { label: __("Nothing: a target only"), value: "" },
    ...(props.measures[type] ?? []).map((m) => ({
      label: MEASURE_LOOK[m].label,
      value: m,
    })),
  ];
}

// what each saved target counted from, so a measure changed in the form shows no stale count
const savedMeasure = Object.fromEntries(
  props.start.map((c) => [c.criterion, c.measure || ""])
);
/** The row's progress, live against the figure as it is edited. */
function rowResult(row: Row) {
  const measured = props.progress?.criteria?.[row.criterion];
  if (!measured || !row.measure || savedMeasure[row.criterion] !== row.measure)
    return null;
  return progressOf(row, measured, props.progress!, props.currency);
}
const problemId = (row: Row) => `${formId}-problem-${row.key}`;

function remove(key: number) {
  criteria.value = criteria.value.filter((c) => c.key !== key);
  delete problems[key];
}

// ---------- adding a target ----------

const newName = ref("");
// "Info" is a Text target that is information only
const newType = ref<ValueType | "Info">("Number");
const addProblem = ref("");

function add() {
  const name = newName.value.trim();
  if (!name) {
    addProblem.value = __("Give the target a name.");
    return;
  }
  if (
    criteria.value.some((c) => c.criterion.toLowerCase() === name.toLowerCase())
  ) {
    addProblem.value = __("{0} is already on the list.", name);
    return;
  }
  const info = newType.value === "Info";
  const row: Row = {
    criterion: name,
    value_type: info ? "Text" : (newType.value as ValueType),
    target: null,
    measure: "",
    info_only: info ? 1 : 0,
    key: nextKey++,
  };
  criteria.value.push(row);
  newName.value = "";
  addProblem.value = "";
  // straight on to its figure
  nextTick(() => document.getElementById(inputId(row))?.focus());
}

// ---------- assigning ----------

const saving = ref(false);
const error = ref("");

const assignLabel = computed(() =>
  props.people.length === 1
    ? __("Assign to {0}", props.people[0].full_name)
    : __("Assign to {0} people", String(props.people.length))
);

/** Who already has targets for the month, and so has them replaced. */
const replaceNote = computed(() => {
  const had = props.people.filter((p) => p.target);
  const month = monthTitle(props.month);
  if (!had.length) return "";
  if (props.people.length === 1)
    return __(
      "These are {0}'s targets for {1}. Change any figure, then assign to save them.",
      had[0].full_name,
      month
    );
  return __(
    "{0} of the {1} people already have targets for {2}. Assigning replaces theirs with these.",
    String(had.length),
    String(props.people.length),
    month
  );
});

function problemOf(row: Row) {
  const blank = row.target === null || String(row.target).trim() === "";
  if (blank) return __("Fill in a figure, or remove this target.");
  if (row.value_type === "Text") return "";
  const value = Number(row.target);
  if (Number.isNaN(value)) return __("Enter a number.");
  if (value < 0) return __("The target can't be below 0.");
  if (row.value_type === "Percent" && value > 100)
    return __("A percent can't be over 100.");
  return "";
}

function check() {
  let first: Row | undefined;
  for (const row of criteria.value) {
    const problem = problemOf(row);
    if (problem) {
      problems[row.key] = problem;
      first ??= row;
    } else delete problems[row.key];
  }
  if (first) document.getElementById(inputId(first))?.focus();
  return !first;
}

async function assign() {
  error.value = "";
  if (saving.value || !check()) return;
  saving.value = true;
  try {
    const result = await call("helpdesk.api.sales_targets.assign_targets", {
      month: props.month,
      employees: props.people.map((p) => p.user),
      criteria: criteria.value.map(
        ({ criterion, value_type, target, measure, info_only }) => ({
          criterion,
          value_type,
          target:
            value_type === "Text" ? String(target).trim() : Number(target),
          measure: value_type === "Text" ? "" : measure || "",
          info_only: value_type === "Text" && info_only ? 1 : 0,
        })
      ),
    });
    toast.success(
      result.assigned === 1
        ? __(
            "Targets for {0} assigned to {1}",
            monthTitle(props.month),
            props.people[0].full_name
          )
        : __(
            "Targets for {0} assigned to {1} people",
            monthTitle(props.month),
            String(result.assigned)
          )
    );
    emit("assigned");
  } catch (e) {
    error.value = errorText(
      e,
      __("Couldn't assign the targets. Check your connection and try again.")
    );
  } finally {
    saving.value = false;
  }
}
</script>
