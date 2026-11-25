<template>
  <Combobox
    v-model="model"
    :options="shown"
    :label="label"
    :placeholder="placeholder"
    :loading="loading"
    :empty-text="__('Nothing found')"
    open-on-focus
    @update:query="onQuery"
  />
</template>

<script setup lang="ts">
// A customer or agent picker for use inside a Dialog: frappe-ui's Combobox keeps its list in the
// dialog's focus scope, where Link/Autocomplete opens a popover outside it and breaks Escape and
// outside clicks (review of #351). It searches on the server as the person types; only the
// latest search fills the list.
import { __ } from "@/translation";
import { useDebounceFn } from "@vueuse/core";
import { call, Combobox } from "frappe-ui";
import { computed, onMounted, ref, watch } from "vue";

type Picked = "HD Customer" | "HD Agent";
type Option = { label: string; value: string; description?: string };

const props = defineProps<{
  doctype: Picked;
  label?: string;
  placeholder?: string;
  filters?: Record<string, unknown>;
}>();
const model = defineModel<string>({ default: "" });

// the field people recognise a record by
const TITLE: Record<Picked, string> = {
  "HD Customer": "customer_name",
  "HD Agent": "agent_name",
};

const options = ref<Option[]>([]);
const selected = ref<Option | null>(null);
const loading = ref(false);
let latest = 0;

function asOption(row: Record<string, string>): Option {
  const title = row[TITLE[props.doctype]];
  return {
    label: title || row.name,
    value: row.name,
    description: title && title !== row.name ? row.name : undefined,
  };
}

async function search(query: string) {
  const mine = ++latest;
  loading.value = true;
  const title = TITLE[props.doctype];
  try {
    const rows = (await call("frappe.client.get_list", {
      doctype: props.doctype,
      fields: ["name", title],
      filters: props.filters || {},
      or_filters: query
        ? [
            ["name", "like", `%${query}%`],
            [title, "like", `%${query}%`],
          ]
        : undefined,
      order_by: `${title} asc`,
      limit_page_length: 20,
    })) as Record<string, string>[];
    if (mine === latest) options.value = rows.map(asOption);
  } catch {
    if (mine === latest) options.value = [];
  } finally {
    if (mine === latest) loading.value = false;
  }
}
const onQuery = useDebounceFn((query: string) => search(query || ""), 250);

// the chosen record stays in the list (and so keeps its name) whatever the search shows
watch(
  model,
  async (value) => {
    if (!value) {
      selected.value = null;
      return;
    }
    const known = options.value.find((o) => o.value === value);
    if (known) {
      selected.value = known;
      return;
    }
    try {
      const title = TITLE[props.doctype];
      const row = (await call("frappe.client.get_value", {
        doctype: props.doctype,
        filters: { name: value },
        fieldname: ["name", title],
      })) as Record<string, string> | null;
      if (model.value === value) {
        selected.value = row ? asOption(row) : { label: value, value };
      }
    } catch {
      if (model.value === value) selected.value = { label: value, value };
    }
  },
  { immediate: true }
);

const shown = computed(() => {
  const s = selected.value;
  return s && !options.value.some((o) => o.value === s.value)
    ? [s, ...options.value]
    : options.value;
});

onMounted(() => search(""));
</script>
