<template>
  <div class="flex flex-col gap-5 p-4">
    <p v-if="!who.length" class="text-p-sm text-ink-gray-7">
      {{
        people.length === 1
          ? __("{0} owns no open leads to take back.", people[0].full_name)
          : __("They own no open leads to take back.")
      }}
    </p>
    <template v-else>
      <FormControl
        v-model="scope.what"
        type="select"
        :label="industryMode ? __('Industry') : __('Product')"
        :options="whatOptions"
        :disabled="running || confirming"
      />

      <fieldset
        v-if="withDistricts"
        class="flex flex-col gap-2"
        :disabled="running || confirming"
      >
        <legend class="sr-only">{{ __("Which districts") }}</legend>
        <label
          v-for="option in modeOptions"
          :key="option.value"
          class="flex cursor-pointer items-start gap-3 rounded-xl border px-3.5 py-3 focus-within:ring-2 focus-within:ring-highlight"
          :class="
            scope.mode === option.value
              ? 'border-brand bg-brand-soft'
              : 'border-outline-gray-2 hover:bg-surface-gray-1'
          "
        >
          <input
            v-model="scope.mode"
            type="radio"
            name="take-back-mode"
            :value="option.value"
            class="mt-0.5 size-4 shrink-0 focus:outline-none"
          />
          <span class="flex min-w-0 flex-col gap-0.5">
            <span class="text-sm font-semibold text-ink-gray-9">{{
              option.label
            }}</span>
            <span class="text-p-sm text-ink-gray-6 tabular-nums">{{
              option.help
            }}</span>
          </span>
        </label>
        <div
          v-if="scope.mode === 'some'"
          class="flex max-h-64 flex-col overflow-y-auto rounded-xl border border-outline-gray-2"
        >
          <label
            v-for="row in districtRows"
            :key="row.value"
            class="flex min-h-[40px] cursor-pointer items-center gap-2.5 border-b border-outline-gray-1 px-3 text-sm last:border-0 focus-within:ring-2 focus-within:ring-inset focus-within:ring-highlight"
            :class="
              scope.districts.includes(row.value)
                ? 'bg-brand-soft text-brand-ink'
                : 'text-ink-gray-8 hover:bg-surface-gray-1'
            "
          >
            <Checkbox
              :model-value="scope.districts.includes(row.value)"
              @update:model-value="tick(row.value, !!$event)"
            />
            <span class="min-w-0 flex-1 truncate">{{ row.label }}</span>
            <span class="font-mono tabular-nums text-ink-gray-7">{{
              row.count
            }}</span>
          </label>
        </div>
      </fieldset>

      <!-- what will happen, in numbers; while it runs, how far it got -->
      <div
        class="flex flex-col gap-1 rounded-lg bg-surface-gray-1 px-3.5 py-3 text-p-sm"
        aria-live="polite"
      >
        <template v-if="running">
          <p class="text-ink-gray-9 tabular-nums">
            {{
              __(
                "Sending back: {0} of {1} done.",
                String(done),
                String(total ?? 0)
              )
            }}
          </p>
          <p class="text-ink-gray-6">
            {{ __("Keep this page open until it finishes.") }}
          </p>
        </template>
        <p
          v-else-if="scope.mode === 'some' && !scope.districts.length"
          class="text-ink-gray-7"
        >
          {{ __("Pick at least one district above.") }}
        </p>
        <p v-else-if="total === null" class="text-ink-gray-6">
          {{ countError || __("Counting their leads…") }}
        </p>
        <p v-else-if="!total" class="text-ink-gray-7">
          {{
            __(
              "None of their open leads match. Choose another {0} or district.",
              industryMode ? __("industry") : __("product")
            )
          }}
        </p>
        <p v-else class="text-ink-gray-8">{{ summary }}</p>
      </div>
    </template>

    <ErrorMessage v-if="error" :message="error" role="alert" />
  </div>

  <div
    v-if="who.length"
    class="flex flex-col gap-2 border-t border-outline-gray-2 bg-surface-base p-4 lg:sticky lg:bottom-0"
  >
    <div
      v-if="confirming"
      class="flex flex-col gap-2 rounded-lg bg-danger-soft px-3 py-2.5"
      role="alertdialog"
      :aria-label="__('Send leads back')"
    >
      <p class="text-p-sm text-danger tabular-nums">
        {{
          __(
            "Send {0} leads from {1} back to the pool?",
            String(total),
            whoLabel
          )
        }}
      </p>
      <div class="grid grid-cols-2 gap-2">
        <Button
          variant="solid"
          :label="__('Keep them')"
          :disabled="running"
          @click="confirming = false"
        />
        <Button
          variant="outline"
          theme="red"
          :label="__('Yes, send back')"
          :loading="running"
          :disabled="running"
          @click="sendBack"
        />
      </div>
    </div>
    <Button
      v-else
      variant="outline"
      theme="red"
      size="md"
      :label="
        total
          ? __('Send {0} leads back to the pool', String(total))
          : __('Send leads back to the pool')
      "
      :disabled="running || counting || !total"
      @click="confirming = true"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Checkbox,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import {
  byIndustry,
  hasDistricts,
  type DepartmentLeads,
  type PlanDepartment,
  type PlanMember,
} from "./callPlans";

/**
 * Take back on Assign leads (docs/leads.md, "Assign leads"): the open leads of the people
 * picked go back to the department's unassigned pool, all of them or one product's (or
 * industry's) in some districts. The hub lists and takes back at most 100 at a time, so it
 * works through them in rounds, each reading what the person still has: a lead moved
 * meanwhile is never taken from its new owner.
 */
const props = defineProps<{
  department: PlanDepartment;
  /** the people picked, at least one */
  people: PlanMember[];
}>();
const emit = defineEmits<{
  /** leads went back: the counts on the page are out of date */
  (e: "changed"): void;
}>();

// the most the hub lists in one call
const CHUNK = 100;

const industryMode = computed(() => byIndustry(props.department));
const withDistricts = computed(() => hasDistricts(props.department));

/** The people picked who own open leads. */
const who = computed(() => props.people.filter((m) => m.leads > 0));
const whoLabel = computed(() =>
  who.value.length === 1
    ? who.value[0].full_name
    : __("{0} people", String(who.value.length))
);
const scope = reactive<{
  what: string;
  mode: "all" | "some";
  districts: string[];
}>({ what: "", mode: "all", districts: [] });
/** {user: {district or "": open leads}} in the scope chosen; null while counting */
const owned = ref<Record<string, Record<string, number>> | null>(null);
/** their open leads per product, industry and district, whatever the scope */
const spread = ref<{
  products: Record<string, number>;
  industries: Record<string, number>;
  districts: Record<string, number>;
}>({ products: {}, industries: {}, districts: {} });
const counting = ref(false);
const countError = ref("");
const running = ref(false);
const confirming = ref(false);
const done = ref(0);
const error = ref("");

const total = computed(() =>
  owned.value === null
    ? null
    : Object.values(owned.value)
        .flatMap((byDistrict) => Object.values(byDistrict))
        .reduce((sum, n) => sum + n, 0)
);
const firstName = (member: PlanMember) => member.full_name.split(" ")[0];
const summary = computed(() =>
  who.value.length === 1
    ? __(
        "{0} leads go back to {1}'s unassigned pool. {2} will no longer see them or their notes, and their calls not made yet leave {2}'s list.",
        String(total.value),
        props.department.department,
        firstName(who.value[0])
      )
    : __(
        "{0} leads go back to {1}'s unassigned pool. They will no longer see them or their notes, and their calls not made yet leave their lists.",
        String(total.value),
        props.department.department
      )
);

const sum = (counts: Record<string, number>) =>
  Object.values(counts).reduce((a, b) => a + b, 0);

/** A choice of `all` with every lead, then each name the people have leads of, with how many;
 * `none` ("-") for the leads without one. */
function choices(counts: Record<string, number>, all: string, none: string) {
  return [
    { label: `${all} (${sum(counts)})`, value: "" },
    ...Object.entries(counts)
      .filter(([name, n]) => name && n)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, n]) => ({ label: `${name} (${n})`, value: name })),
    ...(counts[""] ? [{ label: `${none} (${counts[""]})`, value: "-" }] : []),
  ];
}
const whatOptions = computed(() =>
  industryMode.value
    ? choices(spread.value.industries, __("All industries"), __("No industry"))
    : choices(spread.value.products, __("All products"), __("No product"))
);
const modeOptions = computed(() => [
  {
    value: "all",
    label: __("All districts"),
    help: __("{0} leads", String(sum(spread.value.districts))),
  },
  {
    value: "some",
    label: __("Only some districts"),
    help: __("Pick them below."),
  },
]);
/** Their districts, the fullest first; "-" for the leads without one. */
const districtRows = computed(() =>
  Object.entries(spread.value.districts)
    .filter(([, n]) => n)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
    .map(([name, n]) => ({
      label: name || __("No district"),
      value: name || "-",
      count: n,
    }))
);

function tick(district: string, on: boolean) {
  // a ticked box can report twice (the label and the box): never list a district twice
  scope.districts = on
    ? [...new Set([...scope.districts, district])]
    : scope.districts.filter((d) => d !== district);
}

/** The districts to take from: null for all. */
const districts = computed<(string | null)[]>(() =>
  scope.mode === "some" ? scope.districts : [null]
);

function leadsOf(
  member: PlanMember,
  district: string | null,
  pageLength: number
) {
  return call("helpdesk.api.call_batches.get_department_leads", {
    department: props.department.department,
    owner: member.user,
    ...(industryMode.value
      ? { industry: scope.what || null }
      : { product: scope.what || null }),
    district,
    start: 0,
    page_length: pageLength,
  }) as Promise<DepartmentLeads>;
}

// an answer for an older scope must not land over the newest one
let asked = 0;
async function count() {
  const ask = ++asked;
  counting.value = true;
  countError.value = "";
  owned.value = null;
  confirming.value = false;
  try {
    const answers = await Promise.all(
      who.value.map((m) =>
        Promise.all(districts.value.map((d) => leadsOf(m, d, 1)))
      )
    );
    if (ask !== asked) return;
    owned.value = Object.fromEntries(
      who.value.map((m, i) => [
        m.user,
        Object.fromEntries(
          districts.value.map((d, j) => [d ?? "", answers[i][j].total])
        ),
      ])
    );
    // the spread ignores the scope: the same on every answer of a person
    const add = (
      key: "products" | "industries" | "districts"
    ): Record<string, number> => {
      const sums: Record<string, number> = {};
      for (const personal of answers)
        for (const [name, n] of Object.entries(personal[0]?.[key] ?? {}))
          sums[name] = (sums[name] ?? 0) + n;
      return sums;
    };
    spread.value = {
      products: add("products"),
      industries: add("industries"),
      districts: add("districts"),
    };
  } catch (e) {
    if (ask === asked)
      countError.value = errorText(e, __("Couldn't count their leads."));
  } finally {
    if (ask === asked) counting.value = false;
  }
}

// counted again when other people are picked or the scope changes; the page's 15-second
// reload of the same people does not
watch(
  () => who.value.map((m) => `${m.user}:${m.leads}`).join(),
  () => {
    if (running.value) return;
    done.value = 0;
    error.value = "";
    count();
  },
  { immediate: true }
);
watch(
  () => props.department.department,
  () => {
    scope.what = "";
    scope.mode = "all";
    scope.districts = [];
  }
);
watch(
  () => [scope.what, scope.mode, scope.districts.join()],
  () => {
    if (running.value) return;
    if (scope.mode === "some" && !scope.districts.length) {
      owned.value = {};
      confirming.value = false;
      return;
    }
    count();
  }
);

async function sendBack() {
  const counted = owned.value;
  if (!counted || !total.value) return;
  const planned = total.value;
  running.value = true;
  done.value = 0;
  error.value = "";
  let failed = false;
  try {
    for (const member of who.value) {
      for (const district of districts.value) {
        // never more than were counted: leads handed to the person meanwhile stay theirs
        let left = counted[member.user]?.[district ?? ""] ?? 0;
        while (left > 0) {
          const page = await leadsOf(member, district, Math.min(CHUNK, left));
          const names = page.rows.map((r) => r.name);
          if (!names.length) break;
          const result = await call(
            "helpdesk.api.call_batches.unassign_leads",
            {
              department: props.department.department,
              leads: names,
            }
          );
          const moved = Number(result?.unassigned) || 0;
          done.value += moved;
          left -= moved;
          if (!moved) break;
        }
      }
    }
  } catch (e) {
    failed = true;
    error.value = __(
      "{0} of {1} went back before it stopped: {2}",
      String(done.value),
      String(planned),
      errorText(e, __("the ERP site didn't answer."))
    );
  } finally {
    running.value = false;
    confirming.value = false;
  }
  emit("changed");
  if (!failed)
    toast.success(__("Sent {0} leads back to the pool", String(done.value)));
  // the rest, or what is left after a failure, so sending again takes it
  scope.districts = [];
  scope.mode = "all";
  count();
}
</script>
