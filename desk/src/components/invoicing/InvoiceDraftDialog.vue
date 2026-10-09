<template>
  <Dialog
    :open="open"
    :title="created ? __('Invoice draft created') : __('Create invoice draft')"
    :message="customer"
    size="3xl"
    :dismissible="!create.loading"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <!-- done: where the draft is -->
    <div
      v-if="created"
      role="status"
      class="flex items-start gap-3 rounded-lg border border-outline-gray-2 px-4 py-3"
    >
      <LucideCircleCheck
        class="mt-0.5 size-4 shrink-0 text-success"
        aria-hidden="true"
      />
      <div class="min-w-0 text-p-sm text-ink-gray-7">
        <p class="text-base-medium text-ink-gray-9">
          {{ __("Draft {0} is in ERPNext", created.invoice) }}
        </p>
        <p class="mt-1">
          {{
            __(
              "{0} for {1}. It stays a draft until someone submits it in ERPNext; the time logs are marked as billed, so they won't be invoiced again.",
              money(created.amount, created.currency),
              hours(created.hours_billed)
            )
          }}
        </p>
      </div>
    </div>

    <div v-else class="flex flex-col gap-4">
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="periodKey"
          type="select"
          :label="__('Period')"
          :options="periodOptions"
          :disabled="!periodOptions.length"
        />
        <div class="flex items-end pb-1.5">
          <FormControl
            v-model="byTask"
            type="checkbox"
            :label="__('One line per task')"
          />
        </div>
      </div>

      <fieldset v-if="isContractPeriod" class="flex flex-col gap-2">
        <legend class="mb-1 text-xs text-ink-gray-5">
          {{ __("What to bill") }}
        </legend>
        <label
          v-for="option in modeOptions"
          :key="option.value"
          class="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 focus-within:ring-2 focus-within:ring-outline-gray-4"
          :class="
            mode === option.value
              ? 'border-outline-gray-4 bg-surface-gray-1'
              : 'border-outline-gray-2'
          "
        >
          <input
            v-model="mode"
            type="radio"
            name="invoice-mode"
            class="mt-0.5 text-ink-gray-9 focus:ring-0 focus-visible:ring-0"
            :value="option.value"
          />
          <span class="min-w-0">
            <span class="block text-sm text-ink-gray-9">{{
              option.label
            }}</span>
            <span class="block text-p-xs text-ink-gray-6">
              {{ option.help }}
            </span>
          </span>
        </label>
      </fieldset>
      <p v-else-if="preview.data" class="text-p-xs text-ink-gray-6">
        {{
          __(
            "A calendar month bills every billable hour. To bill only the hours beyond a support contract, pick one of its periods."
          )
        }}
      </p>

      <!-- preview -->
      <div
        v-if="preview.loading && !preview.data"
        class="flex flex-col gap-2"
        :aria-label="__('Loading')"
      >
        <span class="h-16 animate-pulse rounded-lg bg-surface-gray-2" />
        <span class="h-28 animate-pulse rounded-lg bg-surface-gray-2" />
      </div>

      <div
        v-else-if="preview.error"
        role="alert"
        class="flex flex-col items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-p-sm text-danger"
      >
        <span class="flex items-start gap-2">
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          {{ errorText(preview.error, __("Couldn't work out the invoice.")) }}
        </span>
        <Button :label="__('Try again')" @click="preview.reload()" />
      </div>

      <template v-else-if="data">
        <dl
          class="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-2"
          :class="preview.loading ? 'opacity-60' : ''"
          :aria-busy="preview.loading"
        >
          <div
            v-for="figure in figures"
            :key="figure.label"
            class="min-w-0 bg-surface-base px-3 py-2.5"
          >
            <dt class="truncate text-xs text-ink-gray-5">{{ figure.label }}</dt>
            <dd class="mt-0.5 font-mono text-base tabular-nums text-ink-gray-9">
              {{ figure.value }}
            </dd>
          </div>
        </dl>

        <p
          v-if="!data.lines.length"
          class="rounded-lg border border-outline-gray-2 px-4 py-6 text-center text-p-sm text-ink-gray-6"
        >
          {{
            data.hours_logged
              ? __(
                  "The contract's included hours cover all the unbilled time in this period. Nothing to bill."
                )
              : __(
                  "No unbilled billable time in this period. Time already on an invoice isn't shown."
                )
          }}
        </p>

        <div
          v-else
          class="overflow-hidden rounded-lg border border-outline-gray-2"
          :class="preview.loading ? 'opacity-60' : ''"
        >
          <table class="hidden w-full text-sm sm:table">
            <caption class="sr-only">
              {{
                __("Invoice lines")
              }}
            </caption>
            <thead>
              <tr
                class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs text-ink-gray-5"
              >
                <th scope="col" class="px-3 py-2 font-normal">
                  {{ groupLabel }}
                </th>
                <th scope="col" class="px-3 py-2 text-right font-normal">
                  {{ __("Hours") }}
                </th>
                <th scope="col" class="px-3 py-2 text-right font-normal">
                  {{ __("Rate") }}
                </th>
                <th scope="col" class="px-3 py-2 text-right font-normal">
                  {{ __("Amount") }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="line in data.lines"
                :key="`${line.project}-${line.task}`"
                class="border-b border-outline-gray-1"
              >
                <th
                  scope="row"
                  class="max-w-0 px-3 py-2 text-left font-normal text-ink-gray-8"
                >
                  <span class="block truncate" :title="line.label">
                    {{ line.label }}
                  </span>
                </th>
                <td
                  class="px-3 py-2 text-right font-mono tabular-nums text-ink-gray-8"
                >
                  {{ line.hours }}
                </td>
                <td
                  class="px-3 py-2 text-right font-mono tabular-nums text-ink-gray-6"
                >
                  {{ money(line.rate, data.currency) }}
                </td>
                <td
                  class="px-3 py-2 text-right font-mono tabular-nums text-ink-gray-8"
                >
                  {{ money(line.amount, data.currency) }}
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="bg-surface-gray-1">
                <th
                  scope="row"
                  class="px-3 py-2 text-left font-medium text-ink-gray-9"
                >
                  {{ __("Total before tax") }}
                </th>
                <td
                  class="px-3 py-2 text-right font-mono font-medium tabular-nums text-ink-gray-9"
                >
                  {{ data.hours_billed }}
                </td>
                <td />
                <td
                  class="px-3 py-2 text-right font-mono font-medium tabular-nums text-ink-gray-9"
                >
                  {{ money(data.amount, data.currency) }}
                </td>
              </tr>
            </tfoot>
          </table>

          <!-- small screens: a two-line row per line -->
          <ul role="list" class="sm:hidden">
            <li
              v-for="line in data.lines"
              :key="`${line.project}-${line.task}`"
              class="flex flex-col gap-0.5 border-b border-outline-gray-1 px-3 py-2.5"
            >
              <span class="truncate text-sm text-ink-gray-8">
                {{ line.label }}
              </span>
              <span
                class="flex justify-between gap-3 font-mono text-xs tabular-nums text-ink-gray-6"
              >
                <span>
                  {{ hours(line.hours) }} ×
                  {{ money(line.rate, data.currency) }}
                </span>
                <span class="text-ink-gray-8">
                  {{ money(line.amount, data.currency) }}
                </span>
              </span>
            </li>
            <li
              class="flex justify-between gap-3 bg-surface-gray-1 px-3 py-2.5 text-sm font-medium text-ink-gray-9"
            >
              <span>{{ __("Total before tax") }}</span>
              <span class="font-mono tabular-nums">
                {{ money(data.amount, data.currency) }}
              </span>
            </li>
          </ul>
        </div>

        <p class="text-p-xs text-ink-gray-6">
          {{ rateNote }}
        </p>
      </template>

      <div
        v-if="create.error"
        role="alert"
        class="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          {{
            errorText(create.error, __("Couldn't create the invoice draft."))
          }}
        </span>
      </div>
    </div>

    <template #actions="{ close }">
      <div class="flex flex-wrap justify-end gap-2">
        <template v-if="created">
          <a
            :href="created.invoice_url"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex h-7 items-center gap-1.5 rounded px-2 text-base text-ink-gray-8 hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ __("Open in ERPNext") }}
            <LucideExternalLink class="size-4" aria-hidden="true" />
            <span class="sr-only">{{ __("(opens in a new tab)") }}</span>
          </a>
          <Button variant="solid" :label="__('Done')" @click="close" />
        </template>
        <template v-else>
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            :label="__('Create invoice draft')"
            :loading="create.loading"
            :disabled="!canCreate"
            @click="submit"
          />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { hours } from "@/composables/supportHours";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, Dialog, FormControl } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideExternalLink from "~icons/lucide/external-link";
import {
  money,
  type CustomerInvoice,
  type InvoiceMode,
  type InvoicePeriodChoice,
  type InvoicePreview,
} from "./invoices";

const props = defineProps<{ open: boolean; customer: string }>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  created: [invoice: CustomerInvoice];
}>();

/** "start|end"; empty lets the server pick the latest ended contract period or last month */
const periodKey = ref("");
const mode = ref<InvoiceMode>("extra");
const byTask = ref(false);
const created = ref<CustomerInvoice | null>(null);

const preview = createResource({
  url: "helpdesk.api.invoices.get_invoice_preview",
  makeParams() {
    const [start, end] = periodKey.value ? periodKey.value.split("|") : [];
    return {
      customer: props.customer,
      start,
      end,
      mode: isContractPeriod.value || !periodKey.value ? mode.value : "all",
      by_task: byTask.value ? 1 : 0,
    };
  },
  onSuccess(result: InvoicePreview) {
    if (!periodKey.value) periodKey.value = `${result.start}|${result.end}`;
  },
});

const data = computed<InvoicePreview | null>(() => preview.data ?? null);

// the choices come with the first answer; keep them while the period changes
const periods = ref<InvoicePeriodChoice[]>([]);
watch(data, (value) => {
  if (value?.periods) periods.value = value.periods;
});

const periodOptions = computed(() =>
  periods.value.map((p) => ({
    value: `${p.start}|${p.end}`,
    label: p.contract
      ? __("{0} · {1}", p.contract_name || p.contract, periodRange(p))
      : dayjs(p.start).format("MMMM YYYY"),
  }))
);

const isContractPeriod = computed(() =>
  periods.value.some(
    (p) => `${p.start}|${p.end}` === periodKey.value && p.contract
  )
);

function periodRange(p: { start: string; end: string }) {
  return `${dayjs(p.start).format("D MMM")} – ${dayjs(p.end).format(
    "D MMM YYYY"
  )}`;
}

const modeOptions = computed(() => {
  const contract = data.value?.contract;
  return [
    {
      value: "extra" as const,
      label: __("Only the hours beyond the contract"),
      help: contract
        ? __(
            "The contract includes {0} this period ({1} not yet counted on an invoice). They cover the earliest work; only the time after them is billed.",
            hours(contract.allowance),
            hours(contract.included_left)
          )
        : __(
            "The contract's included hours cover the earliest work; only the time after them is billed."
          ),
    },
    {
      value: "all" as const,
      label: __("All billable hours"),
      help: __(
        "Every billable hour is billed, including the ones the contract includes. Use it when the contract's hours are billed separately or don't apply."
      ),
    },
  ];
});

const groupLabel = computed(() =>
  byTask.value ? __("Project · task") : __("Project")
);

const figures = computed(() => {
  const d = data.value!;
  return [
    { label: __("Unbilled time"), value: hours(d.hours_logged) },
    { label: __("Covered by contract"), value: hours(d.hours_covered) },
    { label: __("To bill"), value: hours(d.hours_billed) },
  ];
});

const rateNote = computed(() => {
  const d = data.value!;
  const rate = money(d.rate, d.currency);
  return d.rate_from === "contract"
    ? __(
        "{0} an hour, the contract's rate per extra hour. Taxes are added in ERPNext from the settings' template.",
        rate
      )
    : __(
        "{0} an hour, the default rate in Settings → CRM → Invoicing. Taxes are added in ERPNext from the settings' template.",
        rate
      );
});

const create = createResource({
  url: "helpdesk.api.invoices.create_invoice_draft",
  method: "POST",
  makeParams() {
    const d = data.value!;
    return {
      customer: props.customer,
      start: d.start,
      end: d.end,
      mode: d.mode,
      by_task: byTask.value ? 1 : 0,
      expected_hours: d.hours_billed,
    };
  },
  onSuccess(row: CustomerInvoice) {
    created.value = row;
    emit("created", row);
  },
  // shown inline in the dialog
  onError() {},
});

const canCreate = computed(
  () => !!data.value?.lines.length && !preview.loading && !preview.error
);

function submit() {
  if (create.loading || !canCreate.value) return;
  create.submit();
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    created.value = null;
    periodKey.value = "";
    mode.value = "extra";
    byTask.value = false;
    create.reset();
    preview.reload();
  },
  { immediate: true }
);

watch([periodKey, mode, byTask], ([key], [previousKey]) => {
  // cleared on open (that watcher loads), or set from the first answer: no new request
  if (!key || !previousKey) return;
  create.reset();
  preview.reload();
});
</script>
