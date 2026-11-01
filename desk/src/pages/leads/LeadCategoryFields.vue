<template>
  <!-- Combobox layers inside a dialog, so Escape and clicking outside still close it -->
  <Combobox
    :label="__('Industry')"
    :options="industryOptions"
    :placeholder="blank"
    :empty-text="__('No industry matches')"
    :model-value="pick(industry)"
    @update:model-value="(v: string | null) => (industry = unpick(v))"
  />
  <Combobox
    :label="__('State')"
    :options="stateOptions"
    :placeholder="blank"
    :empty-text="__('No state matches')"
    :model-value="pick(state)"
    @update:model-value="(v: string | null) => (state = unpick(v))"
  />
  <div class="flex flex-col gap-1.5">
    <Combobox
      :label="__('District')"
      :options="districtOptions"
      :placeholder="blank"
      :empty-text="__('Type the district')"
      allow-custom-value
      :model-value="pick(district)"
      @update:model-value="(v: string | null) => (district = unpick(v))"
    />
    <p class="text-p-xs text-ink-gray-6">
      {{
        isKerala
          ? __("Kerala's districts are suggested; type any other.")
          : __("Pick one used before, or type it.")
      }}
    </p>
  </div>
  <FormControl
    v-if="options?.org_sizes?.length"
    v-model="orgSize"
    type="select"
    :label="__('Organisation size')"
    :options="sizeChoices"
  />
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useAuthStore } from "@/stores/auth";
import { call, Combobox, FormControl, toast } from "frappe-ui";
import { computed } from "vue";
import { choices, CLEAR, leadOptions, type LeadOptions } from "./leads";

const props = withDefaults(
  defineProps<{
    options?: LeadOptions;
    /** what an empty field means: "Not set" on a lead, "Leave as it is" in bulk */
    blank?: string;
    /** bulk: also offer "Clear", which empties the field on every lead */
    clearable?: boolean;
  }>(),
  { blank: () => __("Not set"), clearable: false }
);

// the four values of a lead form, or of the bulk Set category form
const industry = defineModel<string>("industry", { default: "" });
const state = defineModel<string>("state", { default: "" });
const district = defineModel<string>("district", { default: "" });
const orgSize = defineModel<string>("orgSize", { default: "" });

const KERALA = "Kerala";
// the Combobox cannot hold an empty value, so "no choice" is its own row
const NONE = "__none__";
const pick = (value: string) => value || null;
const unpick = (value: string | null) =>
  !value || value === NONE ? "" : value;

const auth = useAuthStore();
const isKerala = computed(() => state.value === KERALA);

/** The list, with the lead's own value kept when it isn't on it (it was typed or imported). */
function listWith(values: string[], current: string) {
  const list =
    current && !values.includes(current) ? [current, ...values] : values;
  return [
    { label: props.blank, value: NONE },
    ...(props.clearable ? [{ label: __("Clear"), value: CLEAR }] : []),
    ...list.map((v) => ({ label: v, value: v })),
  ];
}

const industryOptions = computed(() => [
  ...listWith(props.options?.industries ?? [], industry.value),
  {
    type: "custom" as const,
    key: "add-industry",
    label: __("Add as a new industry"),
    description: __("Type the name, then pick this"),
    condition: ({ query }: { query: string }) =>
      auth.isManager &&
      !!query.trim() &&
      !(props.options?.industries ?? []).some(
        (i) => i.toLowerCase() === query.trim().toLowerCase()
      ),
    onClick: ({ query }: { query: string }) => addIndustry(query.trim()),
  },
]);
const stateOptions = computed(() =>
  listWith(props.options?.states ?? [], state.value)
);

// Kerala: its 14 districts; another state: the districts leads there already use;
// no state yet: every district in use. Anything else can be typed.
const districtOptions = computed(() => {
  const used = props.options?.districts_by_state ?? {};
  const suggestions = isKerala.value
    ? props.options?.kerala_districts ?? []
    : state.value
    ? used[state.value] ?? []
    : [...new Set(Object.values(used).flat())];
  return listWith(suggestions, district.value);
});

const sizeChoices = computed(() => [
  ...choices(props.options?.org_sizes, props.blank).slice(0, 1),
  ...(props.clearable ? [{ label: __("Clear"), value: CLEAR }] : []),
  ...choices(props.options?.org_sizes),
]);

function addIndustry(name: string) {
  call("helpdesk.api.leads.add_industry", { name })
    .then((result: { name: string; created: boolean }) => {
      industry.value = result.name;
      leadOptions.reload();
      toast.success(
        result.created
          ? __("Industry {0} added", result.name)
          : __("{0} was already an industry", result.name)
      );
    })
    .catch((e: unknown) =>
      toast.error(errorText(e, __("Couldn't add the industry.")))
    );
}
</script>
