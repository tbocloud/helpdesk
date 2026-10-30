<template>
  <div
    class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
    role="group"
    :aria-label="__('Filter by category')"
  >
    <MultiSelect
      v-for="facet in facets"
      :key="facet.key"
      :label="facet.label"
      :placeholder="facet.any"
      :options="facet.options"
      :model-value="model[facet.key]"
      @update:model-value="(v: string[]) => set(facet.key, v)"
    >
      <template #item-suffix="{ item }">
        <span
          v-if="item.count !== undefined"
          class="font-mono text-xs tabular-nums text-ink-gray-6"
          >{{ item.count }}</span
        >
      </template>
    </MultiSelect>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { createResource, MultiSelect } from "frappe-ui";
import { computed } from "vue";
import type { LeadCategories, LeadOptions } from "./leads";

const props = defineProps<{
  options?: LeadOptions;
  modelValue: LeadCategories;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: LeadCategories): void;
}>();

type Counts = Partial<Record<keyof LeadCategories, Record<string, number>>>;

// how many of the person's leads have each value; the filters work without it (an older
// TBO Smart, or a failed read), they just show no counts
const counts = createResource({
  url: "helpdesk.api.leads.get_category_counts",
  auto: true,
  onError() {},
});
defineExpose({ reload: () => counts.reload() });

const model = computed(() => props.modelValue);

/** Values with leads first (most used first), then the rest of `all`; what is selected
 * but unknown (an old link) stays, so it can be taken off. */
function build(key: keyof LeadCategories, all: string[], onlyUsed = false) {
  const used = ((counts.data as Counts | null)?.[key] ?? {}) as Record<
    string,
    number
  >;
  const hasCounts = Object.keys(used).length > 0;
  const byUse = Object.keys(used).sort((a, b) => used[b] - used[a]);
  const rest = onlyUsed && hasCounts ? [] : all.filter((v) => !(v in used));
  const names = [...byUse, ...rest];
  for (const v of props.modelValue[key]) if (!names.includes(v)) names.push(v);
  return names.map((v) => ({
    label: v,
    value: v,
    count: hasCounts ? used[v] ?? 0 : undefined,
  }));
}

const facets = computed(() => {
  const o = props.options;
  const usedDistricts = [
    ...new Set(Object.values(o?.districts_by_state ?? {}).flat()),
  ];
  return [
    {
      key: "industry" as const,
      label: __("Industry"),
      any: __("Any industry"),
      options: build("industry", o?.industries ?? []),
    },
    {
      key: "state" as const,
      label: __("State"),
      any: __("Any state"),
      options: build("state", o?.states ?? []),
    },
    {
      key: "district" as const,
      label: __("District"),
      any: __("Any district"),
      options: build("district", usedDistricts, true),
    },
    {
      key: "org_size" as const,
      label: __("Organisation size"),
      any: __("Any size"),
      options: build("org_size", o?.org_sizes ?? []),
    },
  ];
});

function set(key: keyof LeadCategories, value: string[]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
</script>
