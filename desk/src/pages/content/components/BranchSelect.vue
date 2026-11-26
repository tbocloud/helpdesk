<template>
  <!-- only for customers with branches; the rest never see it -->
  <FormControl
    v-if="options.length > 1"
    v-model="model"
    type="select"
    :label="label"
    :options="options"
    :description="description"
  />
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";
import { computed, watch } from "vue";
import { useCustomerBranches } from "../branches";

const props = defineProps<{
  customer?: string | null;
  label?: string;
  /** what no branch means here, e.g. "Whole customer" */
  emptyLabel?: string;
  description?: string;
}>();
const model = defineModel<string>({ default: "" });
const { branchesOf } = useCustomerBranches();

const options = computed(() => {
  const branches = branchesOf(props.customer, model.value);
  if (!branches.length) return [];
  return [
    { label: props.emptyLabel || __("Whole customer"), value: "" },
    ...branches.map((b) => ({ label: b.branch_name, value: b.name })),
  ];
});

// another customer's branch never stays picked
watch(
  () => props.customer,
  (customer, previous) => {
    if (customer !== previous && model.value) {
      const mine = branchesOf(customer, model.value).some(
        (b) => b.name === model.value
      );
      if (!mine) model.value = "";
    }
  }
);
</script>
