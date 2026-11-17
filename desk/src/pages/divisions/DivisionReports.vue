<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Division reports')"
      :subtitle="
        __('Pick a report, a division and a period; export it as Excel or PDF.')
      "
    >
      <template #right-header>
        <Button
          size="md"
          :label="__('Overview')"
          :route="{ name: 'DivisionOverview', query: route.query }"
        >
          <template #prefix>
            <LucideLayoutDashboard class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="reports.error"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideLock"
          :title="__('These reports aren\'t for you')"
          :message="
            __(
              'They are for Super Admins and the managers of a division. Ask a Super Admin if you need them.'
            )
          "
        />

        <template v-else>
          <DivisionFilters
            v-model:division="division"
            v-model:period="period"
            v-model:custom="custom"
            :options="options"
            :loading="report.loading"
          >
            <FormControl
              variant="outline"
              size="md"
              type="select"
              class="w-full sm:w-64 sm:order-first"
              :label="__('Report')"
              :model-value="reportKey"
              :options="reportOptions"
              @update:model-value="setReport"
            />
          </DivisionFilters>

          <section
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-labelledby="division-report-title"
          >
            <div
              class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-4 py-4"
            >
              <div class="min-w-0 flex-1">
                <h2
                  id="division-report-title"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ report.data?.title || currentTitle }}
                </h2>
                <p v-if="report.data" class="text-p-xs text-ink-gray-6">
                  {{ periodText }}
                  <template v-if="report.data.currency">
                    · {{ __("Money in {0}", report.data.currency) }}
                  </template>
                </p>
              </div>
              <Button
                size="md"
                :label="__('Excel')"
                :disabled="!canExport"
                @click="exportAs('xlsx')"
              >
                <template #prefix>
                  <LucideFileSpreadsheet class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                size="md"
                :label="__('PDF')"
                :disabled="!canExport"
                @click="exportAs('pdf')"
              >
                <template #prefix>
                  <LucideFileDown class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>

            <div
              v-for="problem in report.data?.errors || []"
              :key="problem.division"
              role="status"
              class="flex items-start gap-2 border-b border-outline-gray-1 bg-warning-soft px-4 py-3 text-p-sm text-warning"
            >
              <LucideTriangleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span>
                {{
                  __(
                    "{0}: customers and quotations are unknown ({1})",
                    problem.division,
                    problem.error
                  )
                }}
              </span>
            </div>

            <TaskyState
              v-if="!range"
              class="py-10"
              :icon="LucideCalendarRange"
              :title="__('Pick both dates')"
              :message="__('Choose a from and a to date to see that period.')"
            />
            <TaskyState
              v-else-if="report.error"
              class="py-10"
              error
              :icon="LucideCircleAlert"
              :title="__('Couldn\'t load the report')"
              :message="errorText(report.error, __('Try again in a minute.'))"
            >
              <Button :label="__('Try again')" @click="report.reload()" />
            </TaskyState>
            <div
              v-else-if="!report.data"
              class="flex flex-col gap-2 p-4"
              aria-busy="true"
              :aria-label="__('Loading')"
            >
              <div
                v-for="i in 5"
                :key="i"
                class="h-10 animate-pulse rounded-lg bg-surface-gray-3"
              />
            </div>
            <TaskyState
              v-else-if="!report.data.rows.length"
              class="py-10"
              :icon="LucideFileSearch"
              :title="__('Nothing to report')"
              :message="
                __('There are no records for this division and period.')
              "
            />
            <div
              v-else
              class="overflow-x-auto"
              :class="report.loading ? 'opacity-60' : ''"
            >
              <table class="w-full text-sm">
                <caption class="sr-only">
                  {{
                    report.data.title
                  }}
                </caption>
                <thead>
                  <tr
                    class="h-11 bg-surface-gray-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
                  >
                    <th
                      v-for="(column, i) in report.data.columns"
                      :key="column.key"
                      scope="col"
                      class="whitespace-nowrap px-3"
                      :class="[
                        column.kind === 'text' ? 'text-left' : 'text-right',
                        i === 0 ? 'pl-4' : '',
                      ]"
                    >
                      {{ column.label }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, r) in report.data.rows"
                    :key="r"
                    class="h-14 border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
                  >
                    <td
                      v-for="(column, i) in report.data.columns"
                      :key="column.key"
                      class="whitespace-nowrap px-3"
                      :class="[
                        column.kind === 'text'
                          ? 'text-left text-ink-gray-9'
                          : 'text-right font-mono tabular-nums text-ink-gray-8',
                        i === 0 ? 'pl-4 font-medium' : '',
                      ]"
                    >
                      {{
                        reportCell(
                          column.kind,
                          row[column.key],
                          report.data.currency
                        )
                      }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  usePageMeta,
} from "frappe-ui";
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileDown from "~icons/lucide/file-down";
import LucideFileSearch from "~icons/lucide/file-search";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideLock from "~icons/lucide/lock";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import DivisionFilters from "./DivisionFilters.vue";
import { OVERVIEW_API, reportCell, type Report } from "./divisions";
import { useDivisionFilters } from "./useDivisionFilters";

usePageMeta(() => ({ title: __("Division reports") }));

const route = useRoute();
const router = useRouter();
const { division, period, custom, range, params } = useDivisionFilters();

const reports = createResource<{
  reports: { key: string; title: string }[];
  options: { name: string; division_name: string }[];
}>({
  url: `${OVERVIEW_API}.get_reports`,
  auto: true,
});
const options = computed(() => reports.data?.options || []);

const reportKey = computed(() => String(route.query.report || "leads"));
const reportOptions = computed(() =>
  (reports.data?.reports || []).map((r) => ({ label: r.title, value: r.key }))
);
const currentTitle = computed(
  () =>
    reports.data?.reports.find((r) => r.key === reportKey.value)?.title || ""
);

function setReport(key: string) {
  router.replace({ query: { ...route.query, report: key } });
}

const reportParams = computed(() => ({
  report: reportKey.value,
  ...params.value,
}));

const report = createResource<Report>({
  url: `${OVERVIEW_API}.get_report`,
  makeParams: () => reportParams.value,
});

watch(
  reportParams,
  () => {
    if (range.value) report.reload();
  },
  { immediate: true }
);

const periodText = computed(() =>
  report.data
    ? __(
        "{0} to {1}",
        dayjs(report.data.from_date).format("D MMM YYYY"),
        dayjs(report.data.to_date).format("D MMM YYYY")
      )
    : ""
);

const canExport = computed(
  () => !!range.value && !!report.data && !report.loading
);

function exportAs(fileFormat: "xlsx" | "pdf") {
  const query = new URLSearchParams({
    report: reportKey.value,
    file_format: fileFormat,
    division: division.value,
    ...(range.value || {}),
  });
  window.open(`/api/method/${OVERVIEW_API}.export_report?${query}`, "_blank");
}
</script>
