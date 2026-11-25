<template>
  <div class="flex flex-col gap-4">
    <p
      role="note"
      class="flex items-start gap-2 rounded-lg bg-info-soft px-3 py-2.5 text-p-sm text-info"
    >
      <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>
        {{
          __(
            "To add a customer: Set up, add the Production site card, read its apps, then switch Copilot on. The site also needs the new client app, which DevOps installs."
          )
        }}
      </span>
    </p>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <TabButtons
        v-model="show"
        :options="filters"
        :aria-label="__('Show customers')"
      />
      <div class="w-full sm:w-72">
        <FormControl
          v-model="query"
          type="text"
          :placeholder="__('Find a customer')"
          :aria-label="__('Find a customer')"
        />
      </div>
    </div>

    <div
      v-if="list.loading && !list.data"
      class="h-64 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
      :aria-label="__('Loading')"
    />
    <ErrorMessage
      v-else-if="list.error && !list.data"
      :message="errorText(list.error, __('Couldn\'t read the customers'))"
    />
    <template v-else>
      <div
        v-if="rows.length"
        class="overflow-x-auto rounded-xl border border-outline-gray-2"
      >
        <table class="w-full min-w-[56rem] text-p-sm">
          <thead>
            <tr class="bg-surface-gray-1 text-left text-ink-gray-5">
              <th scope="col" class="px-4 py-2.5 font-medium">
                {{ __("Customer") }}
              </th>
              <th scope="col" class="px-3 py-2.5 font-medium">
                {{ __("Copilot") }}
              </th>
              <th scope="col" class="px-3 py-2.5 font-medium">
                {{ __("Ready") }}
              </th>
              <th scope="col" class="px-3 py-2.5 font-medium">
                {{ __("Still needed") }}
              </th>
              <th scope="col" class="px-3 py-2.5 text-right font-medium">
                {{ __("Tickets, {0} days", "30") }}
              </th>
              <th scope="col" class="px-4 py-2.5">
                <span class="sr-only">{{ __("Action") }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.customer"
              class="border-t border-outline-gray-1 align-top"
            >
              <td class="px-4 py-3">
                <div class="text-base-medium text-ink-gray-9">
                  {{ row.customer }}
                </div>
                <div class="text-ink-gray-5">
                  {{ row.sites.join(", ") || __("No site") }}
                </div>
              </td>
              <td class="px-3 py-3">
                <Badge
                  :label="row.enabled ? __('On') : __('Off')"
                  :theme="row.enabled ? 'green' : 'gray'"
                  size="sm"
                />
                <div class="mt-1 text-ink-gray-5">
                  {{ row.level ? __(row.level) : __("Default level") }}
                </div>
              </td>
              <td class="px-3 py-3">
                <div class="text-ink-gray-8">
                  {{
                    row.ready.needs.length
                      ? __("{0} of {1}", row.ready.done, row.ready.of)
                      : __("Ready")
                  }}
                </div>
                <div
                  class="mt-1.5 h-1.5 w-28 overflow-hidden rounded-full bg-surface-gray-2"
                  aria-hidden="true"
                >
                  <div
                    class="h-1.5 rounded-full"
                    :class="
                      row.ready.needs.length ? 'bg-warning' : 'bg-success'
                    "
                    :style="{
                      width: `${(row.ready.done / row.ready.of) * 100}%`,
                    }"
                  />
                </div>
              </td>
              <td class="px-3 py-3">
                <div class="flex flex-wrap gap-1">
                  <Badge
                    v-for="need in row.ready.needs"
                    :key="need"
                    :label="need"
                    theme="red"
                    size="sm"
                  />
                  <span v-if="!row.ready.needs.length" class="text-ink-gray-5">
                    -
                  </span>
                </div>
              </td>
              <td
                class="px-3 py-3 text-right font-mono tabular-nums text-ink-gray-8"
              >
                {{ row.tickets }}
              </td>
              <td class="px-4 py-3 text-right">
                <Button
                  :label="__('Set up')"
                  :route="{
                    name: 'Customer',
                    params: { id: row.customer },
                    hash: '#copilot',
                  }"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="text-sm text-ink-gray-5">
        {{
          query
            ? __("No customer matches.")
            : show === "on"
            ? __("No customer has Copilot on yet.")
            : show === "not_ready"
            ? __("Every customer is ready.")
            : __("No customer has a connection or a site card yet.")
        }}
      </p>
      <p class="text-p-xs text-ink-gray-5">
        {{
          __(
            "Customers with a connection or a site card. Tickets: new ones in the last 30 days."
          )
        }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { SETUP_API, type SetupRow } from "@/components/copilot/setupMeta";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Badge,
  Button,
  createResource,
  ErrorMessage,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideInfo from "~icons/lucide/info";
import { useBoardRefresh } from "../boardMeta";

const show = ref<"all" | "on" | "not_ready">("all");
const query = ref("");
const filters = [
  { label: __("All"), value: "all" },
  { label: __("Copilot on"), value: "on" },
  { label: __("Not ready"), value: "not_ready" },
];

const list = createResource({
  url: `${SETUP_API}.customers`,
  makeParams: () => ({ show: show.value }),
  auto: true,
});
watch(show, () => list.reload());
useBoardRefresh(list);

const rows = computed(() => {
  const all = (list.data as SetupRow[] | undefined) || [];
  const q = query.value.trim().toLowerCase();
  if (!q) return all;
  return all.filter(
    (r) =>
      r.customer.toLowerCase().includes(q) ||
      r.sites.some((s) => s.toLowerCase().includes(q))
  );
});
</script>
