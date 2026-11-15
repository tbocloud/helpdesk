<template>
  <div class="flex flex-col gap-5 p-4">
    <p
      class="rounded-lg bg-surface-gray-1 px-3.5 py-3 text-p-sm text-ink-gray-7"
    >
      <template v-if="people.length === 1 && currentKind === 'hand'">
        <span class="font-semibold text-ink-gray-9">{{
          __("No daily plan.")
        }}</span>
        {{
          __("{0} gets leads only when you use Give now.", people[0].full_name)
        }}
      </template>
      <template v-else-if="people.length === 1">
        <span class="font-semibold text-ink-gray-9">{{
          currentKind === "default"
            ? __("Current plan (the department's):")
            : __("Current plan:")
        }}</span>
        <span
          v-for="slot in department.slots"
          :key="slot.label"
          class="block tabular-nums"
          >{{ slot.label }}:
          {{ sharesText(currentShares[slot.label] ?? []) }}</span
        >
      </template>
      <template v-else>
        {{
          __(
            "{0} of {1} have a plan of their own now. Saving gives everyone the plan below.",
            String(people.filter((m) => m.has_plan).length),
            String(people.length)
          )
        }}
      </template>
    </p>

    <FormControl
      v-if="industryMode && choiceOptions.length > 1"
      v-model="choice"
      type="select"
      :label="__('Calls for industry')"
      :options="choiceOptions"
      :disabled="saving || mode === 'default'"
    />
    <FormControl
      v-else-if="!industryMode && (department.products.length > 1 || choice)"
      v-model="choice"
      type="select"
      :label="__('Calls for product')"
      :options="choiceOptions"
      :disabled="saving || mode === 'default' || !!department.campaign_product"
    />

    <fieldset class="flex flex-col gap-2" :disabled="saving">
      <legend class="sr-only">{{ __("Which plan") }}</legend>
      <label
        v-for="option in modeOptions"
        :key="option.value"
        class="flex cursor-pointer items-start gap-3 rounded-xl border px-3.5 py-3 focus-within:ring-2 focus-within:ring-highlight"
        :class="
          mode === option.value
            ? 'border-brand bg-brand-soft'
            : 'border-outline-gray-2 hover:bg-surface-gray-1'
        "
      >
        <input
          v-model="mode"
          type="radio"
          name="plan-mode"
          :value="option.value"
          class="mt-0.5 size-4 shrink-0 focus:outline-none"
        />
        <span class="flex min-w-0 flex-col gap-0.5">
          <span class="text-sm font-semibold text-ink-gray-9">{{
            option.label
          }}</span>
          <span class="text-p-sm text-ink-gray-6">{{ option.help }}</span>
        </span>
      </label>
    </fieldset>

    <!-- each slot: the department's sizes, or rows of district and calls -->
    <div class="flex flex-col gap-3">
      <FormControl
        v-if="mode === 'custom' && !split && withDistricts"
        v-model="wholeDistrict"
        type="select"
        :label="__('District')"
        :options="wholeDistrictOptions"
        :disabled="saving || !!department.campaign_district"
      />
      <section
        v-for="slot in department.slots"
        :key="slot.label"
        class="flex flex-col gap-2 rounded-xl border border-outline-gray-2 p-3"
        :aria-label="slot.label"
      >
        <div class="flex flex-wrap items-baseline gap-x-2">
          <span class="text-sm font-semibold text-ink-gray-9">{{
            slot.label
          }}</span>
          <span class="text-xs text-ink-gray-5 tabular-nums"
            >{{ slot.start_time.slice(0, 5) }}–{{
              slot.end_time.slice(0, 5)
            }}</span
          >
          <span
            class="ml-auto text-sm font-semibold text-ink-gray-8 tabular-nums"
            >{{ __("{0} calls", String(slotTotal(slot.label))) }}</span
          >
        </div>

        <p v-if="mode === 'default'" class="text-p-sm text-ink-gray-7">
          {{ __("{0} mixed, from any district", String(slot.size)) }}
        </p>
        <template v-else>
          <div
            v-for="(row, i) in rows[slot.label]"
            :key="i"
            class="grid grid-cols-[minmax(0,1fr)_4.5rem_2.25rem] items-center gap-2"
          >
            <select
              v-if="split"
              v-model="row.district"
              :class="FIELD"
              :aria-label="
                __('{0} slot, district of row {1}', slot.label, String(i + 1))
              "
              :disabled="saving"
            >
              <option
                v-for="option in districtOptions"
                :key="option.value"
                :value="option.value"
                :disabled="
                  option.value !== row.district &&
                  usedIn(slot.label).includes(option.value)
                "
              >
                {{ option.label }}
              </option>
            </select>
            <span v-else class="truncate text-sm text-ink-gray-7">{{
              wholeDistrict || __("Mixed · any district")
            }}</span>
            <input
              v-model.number="row.calls"
              type="number"
              min="0"
              :max="MAX_CALLS"
              step="5"
              inputmode="numeric"
              :class="[FIELD, 'text-right font-mono tabular-nums']"
              :aria-label="
                __('{0} slot, calls of row {1}', slot.label, String(i + 1))
              "
              :disabled="saving"
            />
            <button
              v-if="split"
              type="button"
              class="grid size-9 place-items-center rounded-[10px] border border-outline-gray-3 text-ink-gray-6 hover:bg-surface-gray-1 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              :aria-label="
                __('Remove row {0} of the {1} slot', String(i + 1), slot.label)
              "
              :disabled="saving"
              @click="rows[slot.label].splice(i, 1)"
            >
              <LucideX class="size-4" aria-hidden="true" />
            </button>
            <p
              v-if="shortText(row)"
              class="col-span-3 flex items-start gap-1.5 text-p-xs text-warning"
            >
              <LucideTriangleAlert
                class="mt-0.5 size-3.5 shrink-0"
                aria-hidden="true"
              />
              <span>{{ shortText(row) }}</span>
            </p>
          </div>
          <p v-if="!rows[slot.label]?.length" class="text-p-sm text-ink-gray-5">
            {{ __("No calls in this slot.") }}
          </p>
          <button
            v-if="split"
            type="button"
            class="self-start rounded text-sm font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:text-ink-gray-4 disabled:no-underline"
            :disabled="saving || !nextFree(slot.label)"
            @click="addRow(slot.label)"
          >
            {{ __("+ Add district") }}
          </button>
        </template>
      </section>
      <p
        v-if="mode === 'custom' && !split && withDistricts"
        class="text-p-xs text-ink-gray-5"
      >
        {{
          __(
            "A different district for each slot needs the latest TBO Smart on the ERP site."
          )
        }}
      </p>
    </div>

    <!-- the day in numbers -->
    <div
      class="flex flex-col gap-1 rounded-lg bg-surface-gray-1 px-4 py-3.5"
      aria-live="polite"
    >
      <p class="text-base font-semibold text-ink-gray-9 tabular-nums">
        {{
          !perPerson
            ? __("No calls planned")
            : people.length > 1
            ? __(
                "{0} calls a day each · {1} together",
                String(perPerson),
                String(perPerson * people.length)
              )
            : __("{0} calls a day", String(perPerson))
        }}
      </p>
      <p v-if="!perPerson" class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Add calls to at least one slot. To stop their automatic calls, use Remove plan."
          )
        }}
      </p>
    </div>

    <!-- whether the pool can carry it -->
    <div v-if="perPerson" class="flex flex-col gap-2" aria-live="polite">
      <template v-if="department.pull_unassigned">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-sm font-semibold text-ink-gray-9">{{
            __("Is the pool enough?")
          }}</span>
          <span class="text-xs text-ink-gray-6 tabular-nums">{{
            __("{0} waiting", waiting.toLocaleString())
          }}</span>
        </div>
        <div
          class="h-2 overflow-hidden rounded-full bg-surface-gray-3"
          role="meter"
          :aria-valuenow="Math.round(Math.min(days, 1) * 100)"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="__('Is the pool enough for a day?')"
        >
          <span
            class="block h-full rounded-full"
            :class="days >= 1 ? 'bg-brand' : 'bg-warning'"
            :style="{ width: `${Math.min(days, 1) * 100}%` }"
          />
        </div>
        <p
          class="flex items-start gap-1.5 rounded-lg px-3 py-2.5 text-p-sm"
          :class="
            days >= 1
              ? 'bg-success-soft text-success'
              : 'bg-warning-soft text-warning'
          "
        >
          <LucideCircleCheck
            v-if="days >= 1"
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <LucideTriangleAlert
            v-else
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>
            {{
              days >= 2
                ? __(
                    "Enough for about {0} days. Each batch uses their own leads first, then the pool.",
                    String(Math.floor(days))
                  )
                : days >= 1
                ? __(
                    "Enough for about a day. Each batch uses their own leads first, then the pool."
                  )
                : __(
                    "Only {0} of the {1} calls a day can come from the pool. Each batch uses their own leads first, then what is left.",
                    String(waiting),
                    String(perPerson * people.length)
                  )
            }}
          </span>
        </p>
      </template>
      <p v-else class="text-p-sm text-ink-gray-6">
        {{
          __(
            "This department doesn't hand out waiting leads, so each person calls their own."
          )
        }}
      </p>
    </div>

    <details class="group text-p-sm text-ink-gray-6">
      <summary
        class="cursor-pointer rounded font-medium text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      >
        {{ __("How daily calls are handed out") }}
      </summary>
      <ul class="mt-2 flex list-disc flex-col gap-1 pl-5">
        <li>
          {{
            __(
              "At the start of each slot, each person gets that slot's calls: their own new leads first, then waiting ones."
            )
          }}
        </li>
        <li v-if="split">
          {{
            __(
              "A district row takes leads of that district. Mixed takes any district, after the named ones."
            )
          }}
        </li>
        <li v-if="autoAssignText(department)">
          {{ autoAssignText(department) }}
        </li>
        <li>
          {{
            __(
              "Calls already handed out stay on their list when you change or remove the plan."
            )
          }}
        </li>
      </ul>
    </details>

    <ErrorMessage v-if="error" :message="error" role="alert" />
  </div>

  <div
    class="flex flex-col gap-2 border-t border-outline-gray-2 bg-surface-base p-4 lg:sticky lg:bottom-0"
  >
    <Button
      variant="solid"
      size="md"
      :label="saveLabel"
      :loading="saving && !removing"
      :disabled="saving || !canSave"
      @click="savePlan"
    />
    <template v-if="withPlan.length">
      <div
        v-if="confirmRemove"
        class="flex flex-col gap-2 rounded-lg bg-danger-soft px-3 py-2.5"
        role="alertdialog"
        :aria-label="__('Remove plan')"
      >
        <p class="text-p-sm text-danger">
          {{
            autoAt
              ? __(
                  "Remove the daily plan for {0}? Automatic calls stop from the next slot, and the {1} top-up skips them. Leads they already own stay with them.",
                  removeLabel,
                  autoAt
                )
              : __(
                  "Remove the daily plan for {0}? Automatic calls stop from the next slot. Leads they already own stay with them.",
                  removeLabel
                )
          }}
        </p>
        <div class="grid grid-cols-2 gap-2">
          <Button
            :label="__('Keep plan')"
            :disabled="saving"
            @click="confirmRemove = false"
          />
          <Button
            variant="solid"
            theme="red"
            :label="__('Remove plan')"
            :loading="saving && removing"
            :disabled="saving"
            @click="removePlan"
          />
        </div>
      </div>
      <Button
        v-else
        variant="outline"
        theme="red"
        :label="__('Remove plan')"
        :disabled="saving"
        @click="confirmRemove = true"
      />
    </template>
    <p class="text-center text-xs text-ink-gray-5">
      {{
        nextSlot
          ? __("Changes take effect from {0}.", nextSlot)
          : __("Changes take effect from the next slot.")
      }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, ErrorMessage, FormControl, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import {
  autoAssignText,
  byIndustry,
  districtLabel,
  hasDistricts,
  industryReady,
  leadsReady,
  memberShares,
  nextSlotText,
  planKind,
  sharesText,
  splitsSlots,
  type PlanDepartment,
  type PlanMember,
} from "./callPlans";

/**
 * Daily plan on Assign leads (docs/leads.md, "Assign leads"): the department's slot sizes, or
 * a plan of their own, each slot split into districts and Mixed rows when the ERP site can
 * (`slot_districts`), else one number per slot and one district. Remove plan leaves them with
 * no daily calls: only the leads given by hand.
 */
const props = defineProps<{
  department: PlanDepartment;
  /** the people picked, at least one */
  people: PlanMember[];
}>();
const emit = defineEmits<{
  /** the department as the ERP site lists it after the save */
  (e: "saved", department: PlanDepartment): void;
}>();

// the ERP site refuses more in a slot
const MAX_CALLS = 500;
const FIELD =
  "h-9 w-full min-w-0 rounded-[10px] border border-outline-gray-3 bg-surface-base px-2.5 text-base text-ink-gray-9 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand-soft disabled:opacity-60";

type Row = { district: string; calls: number | string };

const industryMode = computed(() => byIndustry(props.department));
const withDistricts = computed(() => hasDistricts(props.department));
const split = computed(
  () => withDistricts.value && splitsSlots(props.department)
);
const whoLabel = computed(() =>
  props.people.length === 1
    ? props.people[0].full_name
    : __("{0} people", String(props.people.length))
);
const nextSlot = computed(() => nextSlotText(props.department));
/** "11:00" when the department tops people up automatically, else "". */
const autoAt = computed(() =>
  props.department.auto_assign?.auto_assign
    ? props.department.auto_assign.auto_assign_at.slice(0, 5)
    : ""
);

const first = computed(() => props.people[0]);
const currentKind = computed(() => planKind(props.department, first.value));
const currentShares = computed(() =>
  memberShares(props.department, first.value)
);

const mode = ref<"default" | "custom">("default");
const choice = ref("");
const wholeDistrict = ref("");
const rows = ref<Record<string, Row[]>>({});
const confirmRemove = ref(false);
const saving = ref(false);
const removing = ref(false);
const error = ref("");

const calls = (row: Row) => Number(row.calls) || 0;
const slotSum = (slotRows: Row[]) =>
  slotRows.reduce((sum, r) => sum + calls(r), 0);

/** The first person's plan to edit; the department's sizes as Mixed rows for someone on the
 * department's plan or none. */
function fill() {
  const member = first.value;
  const kind = planKind(props.department, member);
  mode.value = kind === "custom" ? "custom" : "default";
  choice.value =
    props.department.campaign_product ||
    (industryMode.value ? member.industry : member.product) ||
    "";
  wholeDistrict.value =
    props.department.campaign_district || member.district || "";
  const shares =
    kind === "custom" ? memberShares(props.department, member) : null;
  rows.value = Object.fromEntries(
    props.department.slots.map((slot) => [
      slot.label,
      shares
        ? shares[slot.label].map((s) => ({ ...s }))
        : [{ district: "", calls: slot.size }],
    ])
  );
  if (!split.value)
    // one number per slot: the rows of a split plan add up
    for (const slot of props.department.slots)
      rows.value[slot.label] = [
        { district: "", calls: slotSum(rows.value[slot.label]) },
      ];
  confirmRemove.value = false;
  error.value = "";
}

// filled again when other people are picked or their plan changed (a save, or someone else's),
// not on the page's 15-second reload of the same plans
const planKey = computed(() =>
  JSON.stringify([
    props.department.department,
    props.people.map((m) => m.user),
    first.value.has_plan,
    first.value.sizes,
    first.value.slot_districts,
    first.value.product,
    first.value.industry,
    first.value.district,
  ])
);
watch(planKey, fill, { immediate: true });

const modeOptions = computed(() => {
  const sizes = props.department.slots
    .map((s) => `${s.label} ${s.size}`)
    .join(" + ");
  return [
    {
      value: "default",
      label: __("Use the department plan"),
      help: __("{0}, from any district.", sizes),
    },
    {
      value: "custom",
      label: split.value
        ? __("Choose districts for each slot")
        : __("Set calls for each slot"),
      help: split.value
        ? __(
            "For example 50 from one district in the morning, and 20 from another plus 10 mixed in the afternoon."
          )
        : __("Their own number of calls in each slot."),
    },
  ];
});

function readyIn(district: string | null) {
  return industryMode.value
    ? industryReady(props.department, choice.value || null, district)
    : leadsReady(props.department, choice.value || null, district);
}
const waiting = computed(() =>
  readyIn(
    mode.value === "custom" && !split.value ? wholeDistrict.value || null : null
  )
);

const choiceOptions = computed(() => {
  const label = (name: string, value: string | null) =>
    __(
      "{0} · {1} waiting",
      name,
      String(
        industryMode.value
          ? industryReady(props.department, value)
          : leadsReady(props.department, value)
      )
    );
  const names = industryMode.value
    ? props.department.industries ?? []
    : props.department.products.map((p) => p.product_name);
  return [
    {
      label: label(
        industryMode.value ? __("Any industry") : __("Any product"),
        null
      ),
      value: "",
    },
    ...names.map((name) => ({ label: label(name, name), value: name })),
  ];
});

/** Every district the department's leads are in, plus any a row already names (its leads
 * may all be gone); only the campaign district when the department has one. */
const districtNames = computed(() => {
  if (props.department.campaign_district)
    return [props.department.campaign_district];
  const names = new Set(props.department.districts ?? []);
  for (const slotRows of Object.values(rows.value))
    for (const row of slotRows) if (row.district) names.add(row.district);
  return [...names].sort((a, b) => a.localeCompare(b));
});
const districtOptions = computed(() => [
  {
    value: "",
    label: __("Mixed · any district · {0} waiting", String(readyIn(null))),
  },
  ...districtNames.value.map((name) => ({
    value: name,
    label: __("{0} · {1} waiting", name, String(readyIn(name))),
  })),
]);
const wholeDistrictOptions = computed(() => [
  { value: "", label: __("Any district · {0} waiting", String(readyIn(null))) },
  ...districtNames.value.map((name) => ({
    value: name,
    label: __("{0} · {1} waiting", name, String(readyIn(name))),
  })),
]);

const usedIn = (label: string) =>
  (rows.value[label] ?? []).map((r) => r.district);
function nextFree(label: string) {
  const used = usedIn(label);
  return [
    { value: "" },
    ...districtNames.value.map((value) => ({ value })),
  ].find((o) => !used.includes(o.value));
}
function addRow(label: string) {
  const free = nextFree(label);
  if (free) rows.value[label].push({ district: free.value, calls: 10 });
}

function slotTotal(label: string) {
  if (mode.value === "default")
    return props.department.slots.find((s) => s.label === label)?.size ?? 0;
  return slotSum(rows.value[label] ?? []);
}
const perPerson = computed(() =>
  props.department.slots.reduce((sum, slot) => sum + slotTotal(slot.label), 0)
);
const days = computed(() =>
  perPerson.value ? waiting.value / (perPerson.value * props.people.length) : 0
);

/** A named district with fewer waiting leads than the row asks of everyone picked. */
function shortText(row: Row) {
  if (!split.value || !row.district || !calls(row)) return "";
  const there = readyIn(row.district);
  if (there >= calls(row) * props.people.length) return "";
  return there
    ? __(
        "Only {0} waiting in {1}. The rest comes from their own leads there.",
        String(there),
        districtLabel(row.district)
      )
    : __(
        "None waiting in {0}. Calls come from their own leads there.",
        districtLabel(row.district)
      );
}

/** A whole number from 0 to MAX_CALLS in every row, at most MAX_CALLS a slot; else what to fix. */
function invalid(): string {
  if (mode.value === "default") return "";
  for (const slot of props.department.slots) {
    for (const row of rows.value[slot.label] ?? []) {
      const n = Number(row.calls);
      if (!Number.isInteger(n) || n < 0 || n > MAX_CALLS)
        return __(
          "{0}: give a whole number of calls from 0 to {1}.",
          slot.label,
          String(MAX_CALLS)
        );
    }
    if (slotTotal(slot.label) > MAX_CALLS)
      return __(
        "{0} adds up to more than {1} calls. Lower a row.",
        slot.label,
        String(MAX_CALLS)
      );
  }
  return "";
}

const withPlan = computed(() =>
  props.people.filter((m) => planKind(props.department, m) !== "hand")
);
const removeLabel = computed(() =>
  withPlan.value.length === 1
    ? withPlan.value[0].full_name
    : __("{0} people", String(withPlan.value.length))
);
const allDefault = computed(() =>
  props.people.every((m) => planKind(props.department, m) === "default")
);
const canSave = computed(() =>
  mode.value === "default" ? !allDefault.value : perPerson.value > 0
);
const saveLabel = computed(() => {
  if (mode.value === "default")
    return allDefault.value
      ? __("Already on the department plan")
      : __("Use the department plan for {0}", whoLabel.value);
  if (!perPerson.value) return __("Add calls to save a plan");
  return props.people.some((m) => planKind(props.department, m) !== "hand")
    ? __("Save plan for {0}", whoLabel.value)
    : __("Start plan for {0}", whoLabel.value);
});

function choiceParams() {
  return industryMode.value
    ? { product: null, industry: choice.value || null }
    : { product: choice.value || null };
}

async function submit(params: Record<string, unknown>, done: string) {
  error.value = "";
  saving.value = true;
  try {
    const department = await call("helpdesk.api.call_batches.save_call_plan", {
      department: props.department.department,
      ...params,
    });
    toast.success(done);
    confirmRemove.value = false;
    emit("saved", department);
  } catch (e) {
    error.value = errorText(e, __("Couldn't save the plan. Try again."));
  } finally {
    saving.value = false;
    removing.value = false;
  }
}

function savePlan() {
  if (saving.value || !canSave.value) return;
  const users = props.people.map((m) => m.user);
  if (mode.value === "default") {
    submit(
      { users, clear: 1 },
      __("{0} now use the department plan", whoLabel.value)
    );
    return;
  }
  const problem = invalid();
  if (problem) {
    error.value = problem;
    return;
  }
  const slots = props.department.slots;
  submit(
    split.value
      ? {
          users,
          ...choiceParams(),
          slot_districts: Object.fromEntries(
            slots.map((slot) => [
              slot.label,
              rows.value[slot.label]
                .filter((r) => calls(r) > 0)
                .map((r) => ({ district: r.district, calls: calls(r) })),
            ])
          ),
        }
      : {
          users,
          ...choiceParams(),
          district: wholeDistrict.value || null,
          sizes: Object.fromEntries(
            slots.map((slot) => [slot.label, slotTotal(slot.label)])
          ),
        },
    __("Saved the daily plan for {0}", whoLabel.value)
  );
}

/** No calls in any slot: no batches and no top-up; they get only the leads given by hand. */
function removePlan() {
  if (saving.value) return;
  const label = removeLabel.value;
  removing.value = true;
  submit(
    {
      users: withPlan.value.map((m) => m.user),
      sizes: Object.fromEntries(
        props.department.slots.map((s) => [s.label, 0])
      ),
    },
    __("Removed the daily plan for {0}", label)
  );
}
</script>
