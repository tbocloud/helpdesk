<template>
  <SectionCard
    :title="__('Invoices')"
    :count="list.data ? rows.length : undefined"
    :description="
      __(
        'Drafts created from here in ERPNext, newest first. Their status is read from ERPNext.'
      )
    "
    :aria-busy="list.loading"
  >
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>

    <div v-if="list.loading && !list.data" :aria-label="__('Loading')">
      <div
        v-for="i in 3"
        :key="i"
        class="flex items-center gap-4 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
      >
        <span class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2" />
        <span
          class="ml-auto h-3.5 w-1/5 animate-pulse rounded bg-surface-gray-2"
        />
      </div>
    </div>

    <TaskyState
      v-else-if="list.error && !list.data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the invoices')"
      :message="
        errorText(list.error, __('Check your connection and try again.'))
      "
      error
    >
      <Button :label="__('Retry')" @click="list.reload()" />
    </TaskyState>

    <p
      v-else-if="!rows.length"
      class="px-4 py-6 text-center text-p-sm text-ink-gray-6"
    >
      {{
        customer
          ? __("No invoice drafts for this customer yet.")
          : __(
              "No invoice drafts yet. Create one from a contract below or from a customer's Support hours tab."
            )
      }}
    </p>

    <ul v-else role="list">
      <li
        v-for="row in rows"
        :key="row.name"
        class="flex flex-col gap-1.5 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 sm:flex-row sm:items-center sm:gap-4"
      >
        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 flex-wrap items-baseline gap-x-2">
            <a
              :href="row.invoice_url"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex min-w-0 items-center gap-1 rounded font-mono text-sm text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <span class="truncate">{{ row.invoice }}</span>
              <LucideExternalLink
                class="size-3.5 shrink-0 text-ink-gray-5"
                aria-hidden="true"
              />
              <span class="sr-only">{{ __("Open in ERPNext") }}</span>
            </a>
            <RouterLink
              v-if="!customer"
              :to="{
                name: 'Customer',
                params: { id: row.customer },
                hash: '#support-hours',
              }"
              class="min-w-0 truncate rounded text-sm text-ink-gray-7 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              {{ row.customer }}
            </RouterLink>
          </div>
          <p class="text-xs tabular-nums text-ink-gray-5">
            {{ periodText({ start: row.period_start, end: row.period_end }) }}
            ·
            {{
              row.mode === "Extra hours"
                ? __("{0} beyond the contract", hours(row.hours_billed))
                : __("{0} billed", hours(row.hours_billed))
            }}
          </p>
        </div>

        <div class="flex items-center justify-between gap-3 sm:justify-end">
          <span class="font-mono text-sm tabular-nums text-ink-gray-8">
            {{ money(row.amount, row.currency) }}
          </span>
          <span class="flex items-center gap-2">
            <span
              v-if="row.status === 'Linked' && statuses.loading && !status(row)"
              class="text-xs text-ink-gray-5"
            >
              {{ __("Checking…") }}
            </span>
            <TaskyBadge
              v-else-if="look(row)"
              :label="look(row)!.label"
              :tone="look(row)!.tone"
              :icon="look(row)!.icon"
            />
            <Button
              v-if="canUnlink(row)"
              variant="subtle"
              :label="__('Unlink')"
              :loading="unlinking === row.name"
              :tooltip="__('Frees its time logs so they can be invoiced again')"
              @click="unlinkRow(row)"
            />
          </span>
        </div>
      </li>
    </ul>

    <p
      v-if="statuses.error && rows.length"
      class="border-t border-outline-gray-1 px-4 py-2 text-p-xs text-ink-gray-6"
      role="status"
    >
      {{
        __(
          "Couldn't read the statuses from ERPNext: {0}",
          errorText(statuses.error, "")
        )
      }}
      <button
        type="button"
        class="ml-1 rounded underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        @click="loadStatuses()"
      >
        {{ __("Try again") }}
      </button>
    </p>

    <div
      v-if="list.data?.has_more"
      class="border-t border-outline-gray-1 px-4 py-2"
    >
      <Button
        variant="ghost"
        :label="__('Show more')"
        :loading="list.loading"
        @click="showMore"
      />
    </div>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { hours, periodText } from "@/composables/supportHours";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, toast } from "frappe-ui";
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideExternalLink from "~icons/lucide/external-link";
import { money, statusLook, type CustomerInvoice } from "./invoices";

/** One customer's invoices, or everyone's without `customer`. */
const props = defineProps<{ customer?: string }>();

const PAGE = 10;
const limit = ref(PAGE);
const unlinking = ref("");

const list = createResource({
  url: "helpdesk.api.invoices.get_invoices",
  makeParams: () => ({ customer: props.customer, limit: limit.value }),
  auto: true,
  onSuccess() {
    loadStatuses();
  },
});

const rows = computed<CustomerInvoice[]>(() => list.data?.rows ?? []);

// read from ERPNext after the list shows, so the list never waits on the CRM site
const statuses = createResource({
  url: "helpdesk.api.invoices.get_invoice_statuses",
  method: "POST",
  // shown under the list
  onError() {},
});

function loadStatuses() {
  const names = rows.value
    .filter((r) => r.status === "Linked")
    .map((r) => r.name);
  if (names.length) statuses.submit({ names }).catch(() => {});
}

function status(row: CustomerInvoice): string | undefined {
  return (statuses.data as Record<string, string> | undefined)?.[row.name];
}

function look(row: CustomerInvoice) {
  if (row.status === "Unlinked") return statusLook("Unlinked");
  const value = status(row);
  return value ? statusLook(value) : null;
}

function canUnlink(row: CustomerInvoice) {
  const value = status(row);
  return (
    row.status === "Linked" && (value === "Not found" || value === "Cancelled")
  );
}

const unlink = createResource({
  url: "helpdesk.api.invoices.unlink_invoice",
  method: "POST",
  // toasted by unlinkRow
  onError() {},
});

async function unlinkRow(row: CustomerInvoice) {
  unlinking.value = row.name;
  try {
    await unlink.submit({ name: row.name });
    toast.success(
      __("{0} unlinked. Its time can be invoiced again.", row.invoice)
    );
    list.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't unlink the invoice.")));
  } finally {
    unlinking.value = "";
  }
}

function showMore() {
  limit.value += PAGE;
  list.reload();
}

defineExpose({ reload: () => list.reload() });
</script>
