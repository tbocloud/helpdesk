<template>
  <Dialog
    :open="open"
    :title="__('Price the proposal')"
    size="3xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <TaskyState
      v-if="form.error && !data"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the price list')"
      :message="
        errorText(form.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="form.reload()" />
    </TaskyState>
    <div
      v-else-if="!data"
      class="h-64 animate-pulse rounded-lg bg-surface-gray-1"
      aria-busy="true"
      :aria-label="__('Loading')"
    />
    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="save"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{ pricingLine }}
      </p>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <FormControl
          v-model="pkg"
          type="select"
          :label="__('Package')"
          :options="packageOptions"
          :description="__('Fills the lines; you can change them after.')"
          @update:model-value="applyPackage"
        />
        <FormControl
          v-model="values.taxes_and_charges"
          type="select"
          :label="__('Tax')"
          :options="taxOptions"
        />
        <FormControl
          v-model="values.valid_till"
          type="date"
          :label="__('Quotation valid till')"
        />
      </div>

      <fieldset class="flex flex-col gap-2">
        <legend class="mb-1 text-base-medium text-ink-gray-8">
          {{ __("Lines") }}
        </legend>
        <div
          v-for="(line, i) in values.items"
          :key="i"
          class="grid grid-cols-2 gap-2 rounded-lg border border-outline-gray-2 p-3 sm:grid-cols-[1fr_5rem_8rem_6rem_auto]"
        >
          <FormControl
            v-model="line.item_code"
            class="col-span-2 sm:col-span-1"
            type="select"
            :label="__('Service')"
            :options="serviceOptions"
            @update:model-value="setRate(line)"
          />
          <FormControl
            v-model.number="line.qty"
            type="number"
            min="0"
            step="any"
            :label="__('Qty')"
          />
          <FormControl
            v-model.number="line.price_list_rate"
            type="number"
            min="0"
            step="any"
            :label="__('Rate')"
          />
          <FormControl
            v-model.number="line.discount_percentage"
            type="number"
            min="0"
            max="100"
            step="any"
            :label="__('Discount %')"
          />
          <div class="flex items-end">
            <Button
              :label="__('Remove line {0}', String(i + 1))"
              :disabled="values.items.length === 1"
              @click="values.items.splice(i, 1)"
            >
              <template #icon>
                <LucideTrash2 class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <FormControl
            v-model="line.description"
            class="col-span-2 sm:col-span-5"
            :label="__('Description (optional)')"
          />
        </div>
        <div>
          <Button :label="__('Add line')" @click="addLine">
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </fieldset>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model.number="values.additional_discount_percentage"
          type="number"
          min="0"
          max="100"
          step="any"
          :label="__('Extra discount on the total %')"
        />
        <dl class="flex flex-col gap-1 text-sm">
          <div class="flex justify-between gap-4 text-ink-gray-7">
            <dt>{{ __("Discount overall") }}</dt>
            <dd class="font-mono tabular-nums">{{ discountPercent }}%</dd>
          </div>
          <div class="flex justify-between gap-4 text-ink-gray-7">
            <dt>{{ __("Before tax") }}</dt>
            <dd class="font-mono tabular-nums">{{ fmt(net) }}</dd>
          </div>
          <div
            class="flex justify-between gap-4 text-base-medium text-ink-gray-9"
          >
            <dt>{{ __("Total, about") }}</dt>
            <dd class="font-mono tabular-nums">{{ fmt(total) }}</dd>
          </div>
        </dl>
      </div>

      <div
        v-if="aboveBand"
        role="status"
        class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
      >
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        <span>{{ aboveBand }}</span>
      </div>
      <p v-if="error" role="alert" class="text-p-sm text-danger">{{ error }}</p>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Save pricing')"
          :loading="saving.loading"
          :disabled="!data"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, FormControl } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { PricingForm, Proposal, QuotationLine } from "./proposals";

const props = defineProps<{ open: boolean; proposal: string }>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "saved", proposal: Proposal): void;
}>();

const formId = `proposal-pricing-${useId()}`;
const error = ref("");
const pkg = ref("");
const values = reactive({
  taxes_and_charges: "",
  valid_till: "",
  additional_discount_percentage: 0,
  items: [] as QuotationLine[],
});

const form = createResource({
  url: "helpdesk.api.proposals.get_pricing_form",
  makeParams: () => ({ name: props.proposal }),
  onSuccess(d: PricingForm) {
    values.taxes_and_charges = d.taxes_and_charges || "";
    values.valid_till = d.valid_till || "";
    values.additional_discount_percentage =
      d.additional_discount_percentage || 0;
    values.items = d.items?.length
      ? d.items.map((l) => ({ ...l }))
      : [blankLine()];
    pkg.value = "";
  },
});
const data = computed(() => form.data as PricingForm | undefined);

watch(
  () => props.open,
  (open) => {
    if (open) {
      error.value = "";
      form.reload();
    }
  },
  { immediate: true }
);

const services = computed(() => data.value?.catalogue.services ?? []);
const serviceOptions = computed(() => [
  { label: __("Choose a service"), value: "" },
  ...services.value.map((s) => ({ label: s.item_name, value: s.item_code })),
]);
const packageOptions = computed(() => [
  { label: __("None"), value: "" },
  ...(data.value?.catalogue.packages ?? []).map((p) => ({
    label: p.package_name,
    value: p.name,
  })),
]);
const taxOptions = computed(() => [
  { label: __("No tax"), value: "" },
  ...(data.value?.tax_templates ?? []).map((t) => ({ label: t, value: t })),
]);

function blankLine(): QuotationLine {
  return {
    item_code: "",
    qty: 1,
    price_list_rate: 0,
    discount_percentage: 0,
    description: "",
  };
}

function addLine() {
  values.items.push(blankLine());
}

function setRate(line: QuotationLine) {
  const service = services.value.find((s) => s.item_code === line.item_code);
  if (service) line.price_list_rate = service.rate;
}

function applyPackage(name: string) {
  const found = data.value?.catalogue.packages.find((p) => p.name === name);
  if (!found) return;
  values.items = found.items.map((l) => ({
    item_code: l.item_code,
    qty: l.qty,
    price_list_rate: l.rate,
    discount_percentage: 0,
    description: l.description || "",
  }));
}

const listValue = computed(() =>
  values.items.reduce(
    (sum, l) => sum + (Number(l.qty) || 0) * (Number(l.price_list_rate) || 0),
    0
  )
);
const net = computed(() => {
  const lines = values.items.reduce(
    (sum, l) =>
      sum +
      (Number(l.qty) || 0) *
        (Number(l.price_list_rate) || 0) *
        (1 - (Number(l.discount_percentage) || 0) / 100),
    0
  );
  return (
    lines * (1 - (Number(values.additional_discount_percentage) || 0) / 100)
  );
});
const total = computed(
  () =>
    net.value *
    (1 + (data.value?.tax_rates?.[values.taxes_and_charges] || 0) / 100)
);
/** As the approval limits read it: everything off the list value. */
const discountPercent = computed(() =>
  listValue.value
    ? Math.round(((listValue.value - net.value) / listValue.value) * 10000) /
      100
    : 0
);
const currency = computed(() => data.value?.currency || "INR");
function fmt(amount: number) {
  return money(amount, currency.value);
}

const pricingLine = computed(() => {
  const p = data.value?.pricing;
  if (!p) return "";
  const list = p.price_list || __("the selling price list");
  const band = p.discount_band
    ? __("Up to {0}% discount needs no approval.", String(p.discount_band))
    : __(
        "This segment has no discount band: a discount above your own limit needs approval."
      );
  return p.segment
    ? `${__("{0} segment, priced from {1}.", p.segment, list)} ${band}`
    : `${__("No segment on this lead, priced from {0}.", list)} ${band}`;
});

const aboveBand = computed(() => {
  const band = data.value?.pricing?.discount_band;
  if (!band || discountPercent.value <= band) return "";
  return __(
    "{0}% is above the {1}% band. Unless your own limit covers it, the proposal can't be sent until it's approved.",
    String(discountPercent.value),
    String(band)
  );
});

const saving = createResource({
  url: "helpdesk.api.proposals.save_pricing",
  method: "POST",
  onSuccess(d: Proposal) {
    emit("saved", d);
    emit("update:open", false);
  },
  onError(e: unknown) {
    error.value = errorText(
      e,
      __("Couldn't save the pricing. Check your connection and try again.")
    );
  },
});

function save() {
  if (saving.loading) return;
  error.value = "";
  const items = values.items.filter((l) => l.item_code);
  if (!items.length) {
    error.value = __("Add at least one service.");
    return;
  }
  saving.submit({
    name: props.proposal,
    values: {
      taxes_and_charges: values.taxes_and_charges || null,
      valid_till: values.valid_till || null,
      additional_discount_percentage:
        Number(values.additional_discount_percentage) || 0,
      package: pkg.value || null,
      items: items.map((l) => ({
        item_code: l.item_code,
        qty: Number(l.qty) || 0,
        price_list_rate: Number(l.price_list_rate) || 0,
        discount_percentage: Number(l.discount_percentage) || 0,
        description: l.description || null,
      })),
    },
  });
}
</script>
