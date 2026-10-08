<template>
  <Dialog
    :open="open"
    :title="contract ? __('Edit contract') : __('New support contract')"
    :message="customer"
    size="xl"
    :dismissible="!save.loading"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.contract_name"
          class="sm:col-span-2"
          :label="__('Contract name')"
          :placeholder="__('e.g. ERPNext AMC 2026-27')"
          required
          autofocus
        />
        <FormControl
          v-model="form.contract_type"
          type="select"
          :label="__('Type')"
          :options="CONTRACT_TYPES.map((t) => ({ label: __(t), value: t }))"
        />
        <FormControl
          v-if="contract"
          v-model="form.status"
          type="select"
          :label="__('Status')"
          :options="CONTRACT_STATUSES.map((s) => ({ label: __(s), value: s }))"
        />
        <TextInput
          v-model="form.start_date"
          type="date"
          :label="__('Start date')"
          required
        />
        <TextInput
          v-model="form.end_date"
          type="date"
          :label="__('End date')"
          :min="form.start_date || undefined"
          required
        />
        <FormControl
          v-model="form.billing_period"
          type="select"
          :label="__('Billing period')"
          :options="BILLING_PERIODS.map((p) => ({ label: __(p), value: p }))"
          :description="
            form.billing_period === 'One-off block'
              ? __('One period from the start date to the end date.')
              : __('Each period starts on the same day as the start date.')
          "
        />
        <TextInput
          v-model.number="form.hours_per_period"
          type="number"
          min="0.5"
          step="0.5"
          :label="
            form.billing_period === 'One-off block'
              ? __('Hours in the block')
              : __('Hours per period')
          "
          required
        />
        <TextInput
          v-model.number="form.alert_threshold"
          type="number"
          min="1"
          max="100"
          step="1"
          :label="__('Alert at (% used)')"
        />
        <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
        <Combobox
          v-model="form.account_manager"
          :label="__('Account manager')"
          :options="agentOptions"
          :placeholder="__('Nobody')"
          :empty-text="__('No matching agent')"
        />
      </div>

      <FormControl
        v-if="form.billing_period !== 'One-off block'"
        v-model="form.rollover_unused"
        type="checkbox"
        :label="__('Roll over unused hours')"
        :description="
          __('Hours left at the end of a period are added to the next one.')
        "
      />

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model.number="form.rate_per_extra_hour"
          type="number"
          min="0"
          step="0.01"
          :label="__('Rate per extra hour (optional)')"
        />
        <Combobox
          v-model="form.currency"
          :label="__('Currency')"
          :options="currencyOptions"
          :loading="currencies.loading"
          :placeholder="__('Pick a currency')"
          :empty-text="__('No matching currency')"
        />
      </div>

      <FormControl
        v-model="form.notes"
        type="textarea"
        :label="__('Notes')"
        :rows="3"
      />

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="contract ? __('Save changes') : __('Create contract')"
          :loading="save.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import {
  BILLING_PERIODS,
  CONTRACT_STATUSES,
  CONTRACT_TYPES,
  type SupportContract,
} from "@/composables/supportHours";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Combobox,
  createListResource,
  createResource,
  dayjs,
  Dialog,
  FormControl,
  TextInput,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";

const DOCTYPE = "HD Support Contract";

const props = defineProps<{
  open: boolean;
  customer: string;
  /** the contract to edit; a new one when empty */
  contract?: SupportContract | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [name: string];
}>();

const formId = `support-contract-${useId()}`;

function blankForm() {
  const start = dayjs().startOf("month");
  return {
    contract_name: "",
    contract_type: "AMC" as SupportContract["contract_type"],
    status: "Active" as SupportContract["status"],
    start_date: start.format("YYYY-MM-DD"),
    end_date: start.add(1, "year").subtract(1, "day").format("YYYY-MM-DD"),
    billing_period: "Monthly" as SupportContract["billing_period"],
    hours_per_period: 10 as number | "",
    alert_threshold: 80 as number | "",
    rollover_unused: false,
    account_manager: null as string | null,
    rate_per_extra_hour: "" as number | "",
    currency: null as string | null,
    notes: "",
  };
}

const form = reactive(blankForm());
const validation = ref("");

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    validation.value = "";
    save.reset();
    const c = props.contract;
    Object.assign(
      form,
      blankForm(),
      c
        ? {
            contract_name: c.contract_name,
            contract_type: c.contract_type,
            status: c.status,
            start_date: c.start_date,
            end_date: c.end_date,
            billing_period: c.billing_period,
            hours_per_period: c.hours_per_period,
            alert_threshold: c.alert_threshold,
            rollover_unused: !!c.rollover_unused,
            account_manager: c.account_manager,
            rate_per_extra_hour: c.rate_per_extra_hour ?? "",
            currency: c.currency,
            notes: c.notes ?? "",
          }
        : {}
    );
    if (!currencies.data && !currencies.loading) currencies.reload();
  },
  { immediate: true }
);

const { users } = useUserStore();
const agentOptions = computed(() =>
  (users.data ?? [])
    .filter((u: { role?: string }) => u.role && u.role !== "Guest")
    .map((u: { name: string; full_name?: string }) => ({
      label: u.full_name || u.name,
      value: u.name,
      description: u.name,
    }))
);

const currencies = createListResource({
  doctype: "Currency",
  filters: { enabled: 1 },
  fields: ["name"],
  orderBy: "name asc",
  pageLength: 500,
});
const currencyOptions = computed(() =>
  (currencies.data ?? []).map((c: { name: string }) => ({
    label: c.name,
    value: c.name,
  }))
);

function values() {
  return {
    contract_name: form.contract_name.trim(),
    contract_type: form.contract_type,
    status: form.status,
    customer: props.customer,
    start_date: form.start_date,
    end_date: form.end_date,
    billing_period: form.billing_period,
    hours_per_period: Number(form.hours_per_period) || 0,
    alert_threshold: Number(form.alert_threshold) || 80,
    rollover_unused: form.rollover_unused ? 1 : 0,
    account_manager: form.account_manager || null,
    rate_per_extra_hour:
      form.rate_per_extra_hour === "" ? null : Number(form.rate_per_extra_hour),
    currency: form.currency || null,
    notes: form.notes,
  };
}

// the server checks the same and more (overlapping contracts)
function check(): string {
  if (!form.contract_name.trim()) return __("Give the contract a name.");
  if (!form.start_date || !form.end_date)
    return __("Set the start and end dates.");
  if (form.end_date < form.start_date)
    return __("The end date can't be before the start date.");
  if (!(Number(form.hours_per_period) > 0))
    return __("Enter how many hours the customer gets each period.");
  const threshold = Number(form.alert_threshold);
  if (!(threshold >= 1 && threshold <= 100))
    return __("Set the alert between 1% and 100% of the hours used.");
  return "";
}

const save = createResource({
  url: props.contract ? "frappe.client.set_value" : "frappe.client.insert",
  makeParams: () =>
    props.contract
      ? { doctype: DOCTYPE, name: props.contract.name, fieldname: values() }
      : { doc: { doctype: DOCTYPE, ...values() } },
  onSuccess(doc: { name: string }) {
    toast.success(
      props.contract ? __("Contract saved") : __("Contract created")
    );
    emit("saved", doc.name);
    emit("update:open", false);
  },
  // shown inline in the dialog
  onError() {},
});

const errorMessage = computed(
  () =>
    validation.value ||
    (save.error ? errorText(save.error, __("Couldn't save the contract.")) : "")
);

function submit() {
  if (save.loading) return;
  validation.value = check();
  if (!validation.value) save.submit();
}
</script>
