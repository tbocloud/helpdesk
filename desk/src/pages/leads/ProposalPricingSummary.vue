<template>
  <!-- the pricing block: the lead's quotation on the ERP site, priced for its segment -->
  <div class="flex flex-col gap-3 rounded-lg bg-surface-gray-1 p-3">
    <p class="text-p-sm text-ink-gray-7">
      <template v-if="pricing.segment">
        {{ __("{0} segment", pricing.segment) }} ·
      </template>
      {{
        pricing.discount_band
          ? __("discount band {0}%", String(pricing.discount_band))
          : __("no discount band")
      }}
    </p>
    <template v-if="q">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <!-- staff only: the ERPNext Quotation behind the price; the client sees the proposal -->
        <a
          v-if="q.desk_url"
          :href="q.desk_url"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1 rounded font-mono text-xs text-ink-gray-6 hover:text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :title="
            __('Internal ERPNext quotation; the client never sees this number')
          "
          :aria-label="__('Open quotation {0} on the ERP site', q.name)"
        >
          {{ q.name }}
          <LucideExternalLink class="size-3" aria-hidden="true" />
        </a>
        <span v-else class="font-mono text-xs text-ink-gray-6">{{
          q.name
        }}</span>
        <TaskyBadge v-if="q.quote_status" :label="__(q.quote_status)" />
        <span class="text-ink-gray-6">{{
          __("{0} lines", String(q.items.length))
        }}</span>
        <span v-if="discount" class="font-mono tabular-nums text-ink-gray-6">{{
          __("{0}% off", String(discount))
        }}</span>
      </div>
      <!-- the same totals as the client's Investment section -->
      <dl class="flex flex-col gap-1 text-sm">
        <div class="flex items-baseline justify-between gap-3">
          <dt class="text-ink-gray-6">{{ __("Net total") }}</dt>
          <dd class="font-mono tabular-nums text-ink-gray-8">
            {{ money(q.net_total, q.currency) }}
          </dd>
        </div>
        <div
          v-for="(tax, k) in taxLines"
          :key="k"
          class="flex items-baseline justify-between gap-3"
        >
          <dt class="min-w-0 truncate text-ink-gray-6">{{ tax.label }}</dt>
          <dd class="font-mono tabular-nums text-ink-gray-8">
            {{ money(tax.amount, q.currency) }}
          </dd>
        </div>
        <div
          class="flex items-baseline justify-between gap-3 border-t border-outline-gray-2 pt-1"
        >
          <dt class="text-ink-gray-8">{{ __("Grand total") }}</dt>
          <dd class="font-mono text-base-medium tabular-nums text-ink-gray-9">
            {{ money(q.grand_total, q.currency) }}
          </dd>
        </div>
      </dl>
      <p
        v-if="!q.total_taxes_and_charges"
        class="flex items-start gap-1.5 text-p-sm text-ink-gray-6"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{
          __(
            "No GST on this price. Pick a tax template in Change pricing, or set the company's default one on the ERP site."
          )
        }}
      </p>
    </template>
    <p v-else class="text-p-sm text-ink-gray-6">
      {{
        __(
          "Not priced yet. Pick a package or services; the price lives on the lead's quotation."
        )
      }}
    </p>

    <div
      v-if="q?.needs_approval.length"
      role="status"
      class="flex flex-col gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
    >
      <div class="flex items-start gap-2">
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        <span>
          <template v-for="(need, i) in q.needs_approval" :key="i">
            {{
              __(
                "{0} {1}% is above your limit of {2}.",
                __(need.kind),
                String(need.percent),
                limitText(need.limit)
              )
            }}
          </template>
          {{
            waiting
              ? __("Approval is requested; Send opens once it's granted.")
              : __("Request approval to send it, or bring it within the limit.")
          }}
        </span>
      </div>
      <div v-if="editable && !waiting">
        <Button
          size="sm"
          :label="__('Request approval')"
          @click="openRequest"
        />
      </div>
    </div>

    <div v-if="editable">
      <Button
        :label="q ? __('Change pricing') : __('Price the proposal')"
        @click="emit('price')"
      >
        <template #prefix>
          <LucideReceipt class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <Dialog
      v-model:open="showRequest"
      :title="__('Request approval')"
      size="md"
    >
      <form :id="formId" class="flex flex-col gap-3" @submit.prevent="request">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "The next level up is told and decides on the ERP site or in the app."
            )
          }}
        </p>
        <FormControl
          v-model="reason"
          type="textarea"
          :rows="3"
          :label="__('Why this pricing')"
          required
        />
        <p v-if="error" role="alert" class="text-p-sm text-danger">
          {{ error }}
        </p>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="__('Request approval')"
            :disabled="!reason.trim()"
            :loading="requestResource.loading"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, FormControl, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideInfo from "~icons/lucide/info";
import LucideReceipt from "~icons/lucide/receipt";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { Proposal } from "./proposals";

const props = defineProps<{ proposal: Proposal; editable: boolean }>();
const emit = defineEmits<{
  (e: "price"): void;
  (e: "changed", proposal: Proposal): void;
}>();

const formId = `proposal-approval-${useId()}`;
const q = computed(() => props.proposal.quotation);
const pricing = computed(() => props.proposal.pricing || {});
const waiting = computed(() => q.value?.quote_status === "Pending Approval");
const discount = computed(() => {
  const quotation = q.value;
  if (!quotation) return 0;
  const list = quotation.items.reduce(
    (sum, l) => sum + l.qty * (l.price_list_rate || 0),
    0
  );
  return list
    ? Math.round(((list - quotation.net_total) / list) * 10000) / 100
    : 0;
});

/** The tax lines as the client's page shows them; one "Taxes" line from an older ERP site. */
const taxLines = computed(() => {
  const quotation = q.value;
  if (!quotation) return [];
  return quotation.taxes?.length
    ? quotation.taxes
    : [{ label: __("Taxes"), amount: quotation.total_taxes_and_charges || 0 }];
});

function limitText(limit: number | null) {
  if (limit === null) return __("no limit");
  return limit > 0 ? `${limit}%` : __("not set");
}

const showRequest = ref(false);
const reason = ref("");
const error = ref("");

function openRequest() {
  reason.value = "";
  error.value = "";
  showRequest.value = true;
}

const requestResource = createResource({
  url: "helpdesk.api.proposals.request_approval",
  method: "POST",
  onSuccess(p: Proposal) {
    showRequest.value = false;
    emit("changed", p);
    toast.success(__("Approval requested"));
  },
  onError(e: unknown) {
    error.value = errorText(e, __("Couldn't request it. Try again."));
  },
});

function request() {
  if (requestResource.loading || !reason.value.trim()) return;
  requestResource.submit({ name: props.proposal.name, reason: reason.value });
}
</script>
