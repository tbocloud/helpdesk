<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-1.5 text-lg-medium">
          <router-link
            :to="{ name: 'ContentCalendar' }"
            class="text-ink-gray-5 hover:text-ink-gray-8"
            >{{ __("Content Calendar") }}</router-link
          >
          <LucideChevronRight
            class="size-4 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="text-ink-gray-9">{{ __("Delivery report") }}</span>
        </div>
      </template>
      <template #right-header>
        <Button
          :label="__('Export to Excel')"
          :tooltip="
            __('Download this report with the current dates and customer')
          "
          :disabled="!rows.length"
          @click="exportReport"
        >
          <template #prefix
            ><LucideDownload class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div
      class="flex flex-wrap items-end gap-3 border-b border-outline-gray-2 px-4 py-3 md:px-5"
    >
      <FormControl
        v-model="filters.from_date"
        type="date"
        :label="__('From')"
        class="w-40"
      />
      <FormControl
        v-model="filters.to_date"
        type="date"
        :label="__('To')"
        class="w-40"
      />
      <Link
        v-model="filters.customer"
        doctype="HD Customer"
        :label="__('Customer')"
        :placeholder="__('All customers')"
        class="w-full sm:w-60"
      />
    </div>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div
          v-if="report.error"
          class="flex items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {{ report.error?.messages?.[0] || __("Couldn't load the report.") }}
          <Button size="sm" :label="__('Retry')" @click="report.reload()" />
        </div>

        <template v-else>
          <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div
              v-for="stat in totals"
              :key="stat.label"
              class="rounded-lg border border-outline-gray-2 bg-surface-base p-4"
            >
              <div class="text-sm text-ink-gray-6">{{ stat.label }}</div>
              <div class="mt-2 text-2xl-semibold tabular-nums text-ink-gray-9">
                <span
                  v-if="report.loading && !report.data"
                  class="inline-block h-7 w-10 animate-pulse rounded bg-surface-gray-2"
                />
                <template v-else>{{ stat.value }}</template>
              </div>
            </div>
          </div>

          <div
            class="mt-5 overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-base"
          >
            <table class="w-full min-w-[720px] text-sm">
              <thead class="bg-surface-gray-1 text-xs text-ink-gray-5">
                <tr>
                  <th class="px-4 py-2.5 text-left font-medium">
                    {{ __("Customer") }}
                  </th>
                  <th class="px-3 py-2.5 text-left font-medium">
                    {{ __("Delivery") }}
                  </th>
                  <th
                    v-for="col in NUMERIC"
                    :key="col.key"
                    class="px-3 py-2.5 text-right font-medium"
                  >
                    {{ col.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="report.loading && !report.data">
                  <td :colspan="NUMERIC.length + 2" class="px-4 py-6">
                    <div
                      class="h-4 w-1/2 animate-pulse rounded bg-surface-gray-2"
                    />
                  </td>
                </tr>
                <tr v-else-if="!rows.length">
                  <td
                    :colspan="NUMERIC.length + 2"
                    class="px-4 py-12 text-center text-p-sm text-ink-gray-6"
                  >
                    {{ __("No posts planned in this period.") }}
                  </td>
                </tr>
                <tr
                  v-for="row in rows"
                  v-else
                  :key="row.customer"
                  class="border-t border-outline-gray-1"
                >
                  <td class="px-4 py-3 text-ink-gray-9">{{ row.customer }}</td>
                  <td class="px-3 py-3">
                    <div
                      class="h-1.5 w-32 overflow-hidden rounded-full bg-surface-gray-2"
                      role="img"
                      :aria-label="
                        __(
                          '{0} of {1} published',
                          String(row.published),
                          String(row.planned)
                        )
                      "
                    >
                      <div
                        class="h-full rounded-full bg-brand"
                        :style="{
                          width: `${
                            row.planned
                              ? (row.published / row.planned) * 100
                              : 0
                          }%`,
                        }"
                      />
                    </div>
                  </td>
                  <td
                    v-for="col in NUMERIC"
                    :key="col.key"
                    class="px-3 py-3 text-right font-mono tabular-nums"
                    :class="
                      col.key === 'overdue' && row.overdue
                        ? 'font-medium text-danger'
                        : 'text-ink-gray-8'
                    "
                  >
                    {{ col.format(row[col.key]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, watch } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideDownload from "~icons/lucide/download";

interface Row {
  customer: string;
  planned: number;
  published: number;
  on_time: number;
  on_time_pct: number;
  overdue: number;
  awaiting_client: number;
  avg_approval_hours: number | null;
}

const count = (v: number | null) => (v ?? 0).toString();
const NUMERIC: { key: keyof Row; label: string; format: (v: any) => string }[] =
  [
    { key: "planned", label: __("Planned"), format: count },
    { key: "published", label: __("Published"), format: count },
    { key: "on_time_pct", label: __("On time"), format: (v) => `${v ?? 0}%` },
    { key: "overdue", label: __("Overdue"), format: count },
    { key: "awaiting_client", label: __("Awaiting client"), format: count },
    {
      key: "avg_approval_hours",
      label: __("Avg approval"),
      format: (v) => (v == null ? "—" : `${v} h`),
    },
  ];

const filters = reactive({
  from_date: dayjs().startOf("month").format("YYYY-MM-DD"),
  to_date: dayjs().endOf("month").format("YYYY-MM-DD"),
  customer: "",
});

// Frappe's report API checks the report's roles, so this works without desk access
const report = createResource({
  url: "frappe.desk.query_report.run",
  makeParams: () => ({
    report_name: "Content Delivery",
    filters: {
      from_date: filters.from_date,
      to_date: filters.to_date,
      ...(filters.customer ? { customer: filters.customer } : {}),
    },
  }),
  auto: true,
});

watch(filters, () => report.reload());

function exportReport() {
  const params = new URLSearchParams({
    from_date: filters.from_date,
    to_date: filters.to_date,
  });
  if (filters.customer) params.set("customer", filters.customer);
  window.open(
    `/api/method/helpdesk.helpdesk.report.content_delivery.content_delivery.export_xlsx?${params}`,
    "_blank"
  );
}

// the report adds a total row; show it in the tiles instead of the table
const allRows = computed<Row[]>(() =>
  (report.data?.result ?? []).filter((r: any) => r && !Array.isArray(r))
);
const rows = computed(() => allRows.value.filter((r) => r.customer));

const totals = computed(() => {
  const sum = (key: keyof Row) =>
    rows.value.reduce((n, r) => n + ((r[key] as number) || 0), 0);
  const published = sum("published");
  return [
    { label: __("Planned"), value: sum("planned") },
    { label: __("Published"), value: published },
    {
      label: __("On time"),
      value: published
        ? `${Math.round((sum("on_time") / published) * 100)}%`
        : "—",
    },
    { label: __("Overdue"), value: sum("overdue") },
  ];
});
</script>
