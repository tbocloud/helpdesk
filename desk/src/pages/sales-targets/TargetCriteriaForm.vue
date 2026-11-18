<template>
  <form class="flex flex-col gap-5 p-4" novalidate @submit.prevent="assign">
    <p
      v-if="replaceNote"
      class="flex items-start gap-2 rounded-lg bg-surface-gray-1 px-3.5 py-3 text-p-sm text-ink-gray-7"
    >
      <LucideInfo
        class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
        aria-hidden="true"
      />
      <span>{{ replaceNote }}</span>
    </p>

    <!-- the criteria, filled in one by one -->
    <fieldset class="flex flex-col gap-4">
      <legend class="mb-3 text-sm font-semibold text-ink-gray-9">
        {{ __("Targets for {0}", monthTitle(month)) }}
      </legend>
      <TaskyState
        v-if="!criteria.length"
        class="rounded-lg border border-dashed border-outline-gray-3 py-8"
        :icon="LucideListPlus"
        :title="__('No criteria')"
        :message="__('Add a criterion below to set a target.')"
      />
      <ol v-else class="flex flex-col gap-4">
        <li
          v-for="(row, index) in criteria"
          :key="row.key"
          class="flex flex-col gap-1.5"
        >
          <div class="flex min-w-0 items-center gap-2">
            <span
              class="grid size-5 shrink-0 place-items-center rounded-full bg-surface-gray-2 text-2xs font-semibold text-ink-gray-7 tabular-nums"
              aria-hidden="true"
              >{{ index + 1 }}</span
            >
            <label
              :for="inputId(row)"
              class="flex min-w-0 flex-1 items-baseline gap-1.5 text-sm font-medium text-ink-gray-8"
            >
              <span class="truncate">{{ row.criterion }}</span>
              <span class="shrink-0 text-xs font-normal text-ink-gray-6">{{
                VALUE_TYPE_LOOK[row.value_type].label
              }}</span>
            </label>
            <Button
              variant="ghost"
              size="sm"
              :aria-label="__('Remove {0}', row.criterion)"
              @click="remove(row.key)"
            >
              <template #icon>
                <LucideX class="size-4 text-ink-gray-6" />
              </template>
            </Button>
          </div>
          <FormControl
            v-if="row.value_type === 'Text'"
            :id="inputId(row)"
            v-model="row.target"
            type="textarea"
            :rows="2"
            :placeholder="__('e.g. 3 case studies published')"
            :error="problems[row.key]"
          />
          <FormControl
            v-else
            :id="inputId(row)"
            v-model="row.target"
            type="number"
            size="md"
            min="0"
            :max="row.value_type === 'Percent' ? 100 : undefined"
            step="any"
            inputmode="decimal"
            :placeholder="PLACEHOLDERS[row.value_type]"
            :error="problems[row.key]"
          >
            <template v-if="row.value_type === 'Amount'" #prefix>
              <span class="text-sm text-ink-gray-6">{{ symbol }}</span>
            </template>
            <template v-else-if="row.value_type === 'Percent'" #suffix>
              <span class="text-sm text-ink-gray-6">%</span>
            </template>
          </FormControl>
        </li>
      </ol>
    </fieldset>

    <!-- the head's own criteria, beyond the five -->
    <div
      class="flex flex-col gap-2 border-t border-outline-gray-2 pt-4"
      role="group"
      :aria-labelledby="addHeading"
    >
      <h3 :id="addHeading" class="text-sm font-semibold text-ink-gray-9">
        {{ __("Add a criterion") }}
      </h3>
      <div class="grid grid-cols-[minmax(0,1fr)_7.5rem] items-start gap-2">
        <FormControl
          v-model="newName"
          type="text"
          size="md"
          :placeholder="__('e.g. Demos given')"
          :aria-label="__('Name of the new criterion')"
          :error="addProblem"
          @keydown.enter.prevent="add"
        />
        <FormControl
          v-model="newType"
          type="select"
          size="md"
          :aria-label="__('What its target is')"
          :options="typeOptions"
        />
      </div>
      <Button
        class="self-start"
        :label="__('Add criterion')"
        :disabled="criteria.length >= MAX_CRITERIA"
        @click="add"
      >
        <template #prefix>
          <LucidePlus class="size-4" />
        </template>
      </Button>
    </div>

    <ErrorMessage v-if="error" :message="error" role="alert" />
    <Button
      type="submit"
      variant="solid"
      size="md"
      :label="assignLabel"
      :loading="saving"
      :disabled="!criteria.length"
    >
      <template #prefix>
        <LucideUserCheck class="size-4" />
      </template>
    </Button>
  </form>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, ErrorMessage, FormControl, toast } from "frappe-ui";
import { computed, nextTick, reactive, ref, useId } from "vue";
import LucideInfo from "~icons/lucide/info";
import LucideListPlus from "~icons/lucide/list-plus";
import LucidePlus from "~icons/lucide/plus";
import LucideUserCheck from "~icons/lucide/user-check";
import LucideX from "~icons/lucide/x";
import {
  currencySymbol,
  monthTitle,
  VALUE_TYPE_LOOK,
  type Criterion,
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

type Row = Criterion & { key: number };

const formId = useId();
const addHeading = useId();
let nextKey = 0;
const criteria = ref<Row[]>(props.start.map((c) => ({ ...c, key: nextKey++ })));
const problems = reactive<Record<number, string>>({});
const symbol = computed(() => currencySymbol(props.currency));
const typeOptions = computed(() =>
  props.valueTypes.map((t) => ({ label: VALUE_TYPE_LOOK[t].label, value: t }))
);

const inputId = (row: Row) => `${formId}-target-${row.key}`;

function remove(key: number) {
  criteria.value = criteria.value.filter((c) => c.key !== key);
  delete problems[key];
}

// ---------- adding a criterion ----------

const newName = ref("");
const newType = ref<ValueType>("Number");
const addProblem = ref("");

function add() {
  const name = newName.value.trim();
  if (!name) {
    addProblem.value = __("Give the criterion a name.");
    return;
  }
  if (
    criteria.value.some((c) => c.criterion.toLowerCase() === name.toLowerCase())
  ) {
    addProblem.value = __("{0} is already on the list.", name);
    return;
  }
  const row: Row = {
    criterion: name,
    value_type: newType.value,
    target: null,
    key: nextKey++,
  };
  criteria.value.push(row);
  newName.value = "";
  addProblem.value = "";
  // straight on to its target
  nextTick(() => document.getElementById(inputId(row))?.focus());
}

// ---------- assigning ----------

const saving = ref(false);
const error = ref("");

const assignLabel = computed(() =>
  props.people.length === 1
    ? __("Assign to {0}", props.people[0].full_name)
    : __("Assign to {0} employees", String(props.people.length))
);

/** Who already has targets for the month, and so has them replaced. */
const replaceNote = computed(() => {
  const had = props.people.filter((p) => p.target);
  const month = monthTitle(props.month);
  if (!had.length) return "";
  if (props.people.length === 1)
    return __(
      "{0} already has targets for {1}. Assigning saves these in their place.",
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
  if (blank) return __("Fill in the target, or remove this criterion.");
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
      criteria: criteria.value.map(({ criterion, value_type, target }) => ({
        criterion,
        value_type,
        target: value_type === "Text" ? String(target).trim() : Number(target),
      })),
    });
    toast.success(
      result.assigned === 1
        ? __(
            "Targets for {0} assigned to {1}",
            monthTitle(props.month),
            props.people[0].full_name
          )
        : __(
            "Targets for {0} assigned to {1} employees",
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
