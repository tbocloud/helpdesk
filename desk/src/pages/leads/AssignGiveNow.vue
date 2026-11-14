<template>
  <div class="flex flex-col gap-5 p-4">
    <FormControl
      v-if="industryMode"
      v-model="choice"
      type="select"
      :label="__('Industry')"
      :options="choiceOptions"
      :disabled="giving"
    />
    <FormControl
      v-else
      v-model="choice"
      type="select"
      :label="__('Product')"
      :options="choiceOptions"
      :disabled="giving || !!department.campaign_product"
      :description="
        department.campaign_product
          ? __(
              '{0} calls only for {1}, set in the department.',
              department.department,
              department.campaign_product
            )
          : undefined
      "
    />

    <!-- 1. the districts to take from, each with what waits there and what they already own -->
    <fieldset
      v-if="withDistricts"
      class="flex min-w-0 flex-col gap-2"
      :disabled="giving"
    >
      <legend class="mb-2 flex w-full items-baseline justify-between gap-2">
        <span class="text-sm font-semibold text-ink-gray-9">{{
          __("1. Where should leads come from?")
        }}</span>
        <button
          v-if="!department.campaign_district && districtRows.length > 1"
          type="button"
          class="rounded text-sm font-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          @click="pickAllWithLeads"
        >
          {{ __("Pick all with leads") }}
        </button>
      </legend>
      <div
        class="flex items-center gap-2.5 px-3 text-xs text-ink-gray-5"
        aria-hidden="true"
      >
        <span class="w-4 shrink-0" />
        <span class="flex-1">{{ __("District") }}</span>
        <span class="w-16 text-right">{{ __("Waiting") }}</span>
        <span v-if="one" class="w-16 text-right">{{ __("They own") }}</span>
      </div>
      <div
        class="flex max-h-64 flex-col overflow-y-auto rounded-xl border border-outline-gray-2"
      >
        <label
          v-for="row in districtRows"
          :key="row.value"
          class="flex min-h-[40px] items-center gap-2.5 border-b border-outline-gray-1 px-3 text-sm last:border-0 focus-within:ring-2 focus-within:ring-inset focus-within:ring-highlight"
          :class="
            !row.count
              ? 'text-ink-gray-5'
              : picked.includes(row.value)
              ? 'cursor-pointer bg-brand-soft text-brand-ink'
              : 'cursor-pointer text-ink-gray-8 hover:bg-surface-gray-1'
          "
        >
          <Checkbox
            :model-value="picked.includes(row.value)"
            :disabled="!row.count || !!department.campaign_district"
            @update:model-value="tick(row.value, !!$event)"
          />
          <span class="min-w-0 flex-1 truncate">{{ row.label }}</span>
          <span
            class="w-16 text-right font-mono tabular-nums"
            :class="row.count ? 'font-semibold' : ''"
            >{{ row.count || __("none") }}</span
          >
          <!-- their own leads: context, not something to give, so it stays gray -->
          <span
            v-if="one"
            class="w-16 text-right font-mono tabular-nums text-ink-gray-6"
            >{{ row.value ? ownedIn(row.value) : "" }}</span
          >
        </label>
      </div>
      <p v-if="department.campaign_district" class="text-p-xs text-ink-gray-6">
        {{
          __(
            "{0} calls only in {1}, set in the department.",
            department.department,
            department.campaign_district
          )
        }}
      </p>
    </fieldset>

    <!-- 2. how many -->
    <div class="flex flex-col gap-2">
      <label :for="countId" class="text-sm font-semibold text-ink-gray-9">{{
        withDistricts
          ? people.length > 1
            ? __("2. How many each?")
            : __("2. How many?")
          : people.length > 1
          ? __("How many each?")
          : __("How many?")
      }}</label>
      <div class="flex flex-wrap items-center gap-2">
        <input
          :id="countId"
          v-model.number="count"
          type="number"
          min="1"
          :max="MAX_GIVE"
          inputmode="numeric"
          class="h-9 w-24 rounded-[10px] border border-outline-gray-3 bg-surface-base px-3 text-right font-mono text-base tabular-nums text-ink-gray-9 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand-soft"
          :disabled="giving"
        />
        <button
          v-for="n in quick"
          :key="n.label"
          type="button"
          class="h-9 rounded-full border px-3 text-sm tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :class="
            count === n.value
              ? 'border-brand bg-brand text-brand-on'
              : 'border-outline-gray-3 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-1'
          "
          :aria-pressed="count === n.value"
          :disabled="giving"
          @click="count = n.value"
        >
          {{ n.label }}
        </button>
      </div>
    </div>

    <!-- what will happen, or what is in the way -->
    <div aria-live="polite">
      <div
        v-if="blocked"
        class="flex items-start gap-2 rounded-lg px-3 py-2.5 text-p-sm"
        :class="
          blocked.tone === 'danger'
            ? 'bg-danger-soft text-danger'
            : blocked.tone === 'warning'
            ? 'bg-warning-soft text-warning'
            : 'bg-surface-gray-1 text-ink-gray-7'
        "
      >
        <LucideTriangleAlert
          v-if="blocked.tone !== 'neutral'"
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        <span>{{ blocked.text }}</span>
      </div>
      <div
        v-else
        class="flex flex-col gap-1.5 rounded-lg bg-surface-gray-1 px-3.5 py-3 text-p-sm"
      >
        <p class="text-base font-semibold text-ink-gray-9">
          {{
            people.length > 1
              ? __("{0} each get {1} leads now", whoLabel, String(count))
              : __("{0} gets {1} leads now", whoLabel, String(count))
          }}
        </p>
        <ul
          v-if="withDistricts"
          class="list-disc pl-5 text-ink-gray-7 tabular-nums"
        >
          <li v-for="part in preview" :key="part.district">
            {{
              __(
                "{0} from {1}",
                String(part.count),
                part.district || __("any district")
              )
            }}
          </li>
        </ul>
        <p class="text-ink-gray-6">
          {{
            nextSlot
              ? __(
                  "They own them at once. Their next batch can call them, at the latest {0}.",
                  nextSlot
                )
              : __("They own them at once. Their next batch can call them.")
          }}
        </p>
      </div>
    </div>

    <ErrorMessage v-if="error" :message="error" role="alert" />
  </div>

  <div
    class="flex flex-col gap-2 border-t border-outline-gray-2 bg-surface-base p-4 lg:sticky lg:bottom-0"
  >
    <Button
      variant="solid"
      size="md"
      :label="giveLabel"
      :loading="giving"
      :disabled="giving || !!blocked"
      @click="give"
    />
    <div class="flex items-center justify-between gap-2">
      <p class="text-xs text-ink-gray-5">
        {{ __("This doesn't change their daily plan.") }}
      </p>
      <Button
        variant="ghost"
        :label="__('Pick leads one by one')"
        :disabled="giving"
        @click="
          emit('pick-leads', choice, picked.length === 1 ? picked[0] : '')
        "
      />
    </div>
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
import { computed, ref, useId, watch } from "vue";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import {
  byIndustry,
  hasDistricts,
  industryReady,
  leadsReady,
  nextSlotText,
  type PlanDepartment,
  type PlanMember,
} from "./callPlans";

/**
 * Give now on Assign leads (docs/leads.md, "Assign leads"): the next unassigned leads of a
 * product (or industry) to each person picked, from the districts ticked, the fullest first.
 * One `assign_leads` call per person and district; their daily plan stays as it is.
 */
const props = defineProps<{
  department: PlanDepartment;
  /** the people picked, at least one */
  people: PlanMember[];
}>();
const emit = defineEmits<{
  /** leads were given: the counts on the page are out of date */
  (e: "changed"): void;
  /** open the Unassigned window on this product (or industry) and district */
  (e: "pick-leads", choice: string, district: string): void;
}>();

// the ERP site refuses more in one call
const MAX_GIVE = 500;
const countId = useId();

const industryMode = computed(() => byIndustry(props.department));
const withDistricts = computed(() => hasDistricts(props.department));
const one = computed(() => props.people.length === 1);
const whoLabel = computed(() =>
  one.value
    ? props.people[0].full_name
    : __("{0} people", String(props.people.length))
);
const nextSlot = computed(() => nextSlotText(props.department));

/** The product, or in industry mode the industry, to give ("" for any). */
const choice = ref("");
const picked = ref<string[]>([]);
const count = ref<number | string>(25);
const giving = ref(false);
const error = ref("");

/** "" (any district) is the first row, so leads without a district can be given too. */
function readyIn(district: string | null) {
  return industryMode.value
    ? industryReady(props.department, choice.value || null, district)
    : leadsReady(props.department, choice.value || null, district);
}

function reset() {
  choice.value = props.department.campaign_product || "";
  picked.value = props.department.campaign_district
    ? [props.department.campaign_district]
    : [];
  error.value = "";
}
watch(() => props.department.department, reset, { immediate: true });

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
  if (industryMode.value)
    return [
      { label: label(__("Any industry"), null), value: "" },
      ...(props.department.industries ?? []).map((name) => ({
        label: label(name, name),
        value: name,
      })),
    ];
  return [
    { label: label(__("Any product"), null), value: "" },
    ...props.department.products.map((p) => ({
      label: label(p.product_name, p.product_name),
      value: p.product_name,
    })),
  ];
});

/** Any district first, then every district, the fullest first; an empty one is listed but
 * can't be ticked. */
const districtRows = computed(() => {
  const names = props.department.campaign_district
    ? [props.department.campaign_district]
    : props.department.districts ?? [];
  const rows = names
    .map((name) => ({ label: name, value: name, count: readyIn(name) }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  if (props.department.campaign_district) return rows;
  return [
    { label: __("Any district"), value: "", count: readyIn(null) },
    ...rows,
  ];
});

// "Any district" and named districts don't mix: the last kind ticked wins
watch(picked, (now, before) => {
  const added = now.filter((d) => !before.includes(d));
  if (added.includes("") && now.length > 1) picked.value = [""];
  else if (added.length && now.includes("") && now.length > 1)
    picked.value = now.filter((d) => d !== "");
});

function tick(district: string, on: boolean) {
  // a ticked box can report twice (the label and the box): never list a district twice
  picked.value = on
    ? [...new Set([...picked.value, district])]
    : picked.value.filter((d) => d !== district);
}

function pickAllWithLeads() {
  picked.value = districtRows.value
    .filter((row) => row.value && row.count)
    .map((row) => row.value);
}

const waitingPicked = computed(() =>
  withDistricts.value
    ? picked.value.reduce((sum, d) => sum + readyIn(d || null), 0)
    : readyIn(null)
);

const quick = computed(() => {
  const each = Math.min(
    Math.floor(waitingPicked.value / props.people.length),
    MAX_GIVE
  );
  const chips = [10, 25, 50, 100].map((n) => ({ label: String(n), value: n }));
  return each > 0 && !chips.some((c) => c.value === each)
    ? [...chips, { label: __("All {0}", String(each)), value: each }]
    : chips;
});

const amount = computed(() => Number(count.value));
const blocked = computed<{
  text: string;
  tone: "neutral" | "warning" | "danger";
} | null>(() => {
  if (!readyIn(null))
    return {
      tone: "warning",
      text: __(
        "No leads are waiting for this {0}. Pick another one, or take leads back from someone first.",
        industryMode.value ? __("industry") : __("product")
      ),
    };
  if (withDistricts.value && !picked.value.length)
    return { tone: "neutral", text: __("Pick at least one district above.") };
  if (!Number.isInteger(amount.value) || amount.value < 1)
    return { tone: "neutral", text: __("Say how many leads to give.") };
  if (amount.value > MAX_GIVE)
    return {
      tone: "danger",
      text: __("Give at most {0} at a time.", String(MAX_GIVE)),
    };
  const need = amount.value * props.people.length;
  if (need > waitingPicked.value)
    return {
      tone: "danger",
      text: withDistricts.value
        ? __(
            "Only {0} leads are waiting in the districts you picked, and you need {1}. Pick more districts or lower the amount.",
            String(waitingPicked.value),
            String(need)
          )
        : __(
            "Only {0} leads are waiting, and you need {1}. Lower the amount.",
            String(waitingPicked.value),
            String(need)
          ),
    };
  return null;
});

/** [{district, count}] for each person in turn, the fullest districts first, out of what is
 * left after the people before them. */
function plan(): { district: string; count: number }[][] {
  const left: Record<string, number> = Object.fromEntries(
    (withDistricts.value ? picked.value : [""]).map((d) => [
      d,
      readyIn(d || null),
    ])
  );
  return props.people.map(() => {
    let need = amount.value;
    const parts: { district: string; count: number }[] = [];
    for (const district of Object.keys(left).sort(
      (a, b) => left[b] - left[a]
    )) {
      if (need <= 0) break;
      const take = Math.min(need, left[district]);
      if (!take) continue;
      parts.push({ district, count: take });
      left[district] -= take;
      need -= take;
    }
    return parts;
  });
}

/** What the first person gets, by district (all of them, for several people). */
const preview = computed(() => {
  if (blocked.value) return [];
  const sums: Record<string, number> = {};
  for (const parts of plan())
    for (const part of parts)
      sums[part.district] = (sums[part.district] ?? 0) + part.count;
  return Object.entries(sums).map(([district, n]) => ({
    district,
    count: n,
  }));
});

const giveLabel = computed(() =>
  blocked.value
    ? __("Give leads to {0}", whoLabel.value)
    : one.value
    ? __("Give {0} leads to {1}", String(amount.value), whoLabel.value)
    : __("Give {0} leads each to {1}", String(amount.value), whoLabel.value)
);

async function give() {
  if (blocked.value || giving.value) return;
  error.value = "";
  giving.value = true;
  const wanted = amount.value * props.people.length;
  let given = 0;
  try {
    const parts = plan();
    for (const [i, member] of props.people.entries()) {
      for (const part of parts[i]) {
        const result = await call("helpdesk.api.call_batches.assign_leads", {
          department: props.department.department,
          user: member.user,
          count: part.count,
          ...(industryMode.value
            ? { industry: choice.value || null }
            : { product: choice.value || null }),
          district: part.district || null,
        });
        given += Number(result?.assigned) || 0;
      }
    }
    if (!given) toast.error(__("No waiting leads were left to give."));
    else if (given < wanted)
      toast.success(
        __(
          "Gave {0} leads to {1}. The rest were taken meanwhile.",
          String(given),
          whoLabel.value
        )
      );
    else
      toast.success(__("Gave {0} leads to {1}", String(given), whoLabel.value));
  } catch (e) {
    error.value = given
      ? __(
          "Gave {0} leads, then it stopped: {1}",
          String(given),
          errorText(e, __("the ERP site didn't answer."))
        )
      : errorText(e, __("Couldn't give the leads. Try again."));
  } finally {
    giving.value = false;
    emit("changed");
  }
}

// how many open leads the one person picked owns in each district: a district at 0 waiting
// can still hold their leads. Asked again only when their lead total changes, not on the
// page's 15-second reload.
const owned = ref<Record<string, number>>({});
const ownedKey = computed(() =>
  one.value && withDistricts.value
    ? `${props.department.department}|${props.people[0].user}|${props.people[0].leads}`
    : ""
);
watch(
  ownedKey,
  async (key) => {
    owned.value = {};
    if (!key) return;
    try {
      const page = await call(
        "helpdesk.api.call_batches.get_department_leads",
        {
          department: props.department.department,
          owner: props.people[0].user,
          page_length: 1,
        }
      );
      if (key === ownedKey.value) owned.value = page.districts ?? {};
    } catch {
      // the column only adds context; giving works without it
    }
  },
  { immediate: true }
);
function ownedIn(district: string) {
  const key = district.toLowerCase();
  return Object.entries(owned.value).reduce(
    (sum, [name, n]) => (name.toLowerCase() === key ? sum + n : sum),
    0
  );
}
</script>
