<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Lead report')"
      :subtitle="
        data
          ? __(
              '{0} · each salesperson\'s leads created or updated in the week',
              data.division_name
            )
          : __('Each salesperson\'s leads created or updated in the week')
      "
    >
      <template #right-header>
        <Button
          size="md"
          variant="solid"
          :label="__('Export to Excel')"
          :disabled="!data?.rows.length"
          @click="exportWeek"
        >
          <template #prefix>
            <LucideFileSpreadsheet class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <div class="flex flex-wrap items-end gap-3">
          <MonthStepper
            v-if="weeks.length"
            v-model="week"
            unit="week"
            :options="weeks"
          />
          <FormControl
            v-if="data?.sees_team"
            v-model="salesperson"
            type="select"
            size="md"
            class="w-full sm:w-56"
            :aria-label="__('Salesperson')"
            :options="personOptions"
          />
        </div>

        <div
          class="flex flex-wrap items-center gap-2"
          role="group"
          :aria-label="__('Filters')"
        >
          <FormControl
            v-model="filters.search"
            type="search"
            size="md"
            class="w-full sm:w-64"
            :aria-label="__('Search')"
            :placeholder="__('Company, contact, number or email')"
            @update:model-value="searchSoon"
          >
            <template #prefix>
              <LucideSearch class="size-4 text-ink-gray-5" aria-hidden="true" />
            </template>
          </FormControl>
          <FormControl
            v-for="filter in filterSelects"
            :key="filter.key"
            v-model="filters[filter.key]"
            type="select"
            size="md"
            class="w-full sm:w-auto"
            :aria-label="filter.label"
            :options="filter.options"
          />
          <Button
            v-if="filtered"
            size="md"
            variant="ghost"
            :label="__('Clear filters')"
            @click="clearFilters"
          />
        </div>

        <TaskyState
          v-if="report.error"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the weekly lead report')"
          :message="errorText(report.error, __('Try again in a minute.'))"
        >
          <Button :label="__('Try again')" @click="report.reload()" />
        </TaskyState>

        <section
          v-else
          class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
          aria-labelledby="weekly-report-title"
        >
          <div class="border-b border-outline-gray-2 px-4 py-4">
            <h2
              id="weekly-report-title"
              class="text-base font-semibold text-ink-gray-9"
            >
              {{ week ? weekLabel(week) : __("This week") }}
            </h2>
            <p v-if="data" class="text-p-xs text-ink-gray-6">
              {{ summary }}
            </p>
          </div>

          <div
            v-if="!data || report.loading"
            class="flex flex-col gap-2 p-4"
            aria-busy="true"
            :aria-label="__('Loading')"
          >
            <div
              v-for="n in 4"
              :key="n"
              class="h-12 animate-pulse rounded-lg bg-surface-gray-1"
            />
          </div>

          <TaskyState
            v-else-if="!data.rows.length && filtered"
            class="py-12"
            :icon="LucideSearchX"
            :title="__('No leads match these filters')"
            :message="
              __('Change or clear the filters to see more of the week.')
            "
          >
            <Button :label="__('Clear filters')" @click="clearFilters" />
          </TaskyState>
          <TaskyState
            v-else-if="!data.rows.length"
            class="py-12"
            :icon="LucideCalendarCheck"
            :title="__('No leads updated this week')"
            :message="
              __(
                'A lead shows here once it is created or changed in the week: fill in its visits, chances and remarks on the lead.'
              )
            "
          />

          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[1150px] text-left text-p-sm">
              <thead class="bg-surface-gray-1 text-p-xs text-ink-gray-6">
                <tr>
                  <th
                    v-if="showPerson"
                    scope="col"
                    class="px-4 py-2 font-medium"
                  >
                    {{ __("Salesperson") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Name") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Contact") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Requirement") }}
                  </th>
                  <th scope="col" class="px-4 py-2 font-medium">
                    {{ __("Quoted") }}
                  </th>
                  <th scope="col" class="w-36 px-4 py-2 font-medium">
                    {{ __("Conversion possibility") }}
                  </th>
                  <th scope="col" class="w-24 px-4 py-2 font-medium">
                    {{ __("Visits this week") }}
                  </th>
                  <th scope="col" class="w-28 px-4 py-2 font-medium">
                    {{ __("Follow-up plan") }}
                  </th>
                  <th scope="col" class="min-w-56 px-4 py-2 font-medium">
                    {{ __("Remarks") }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in data.rows"
                  :key="row.lead"
                  class="border-t border-outline-gray-1 align-top"
                >
                  <td v-if="showPerson" class="px-4 py-3 text-ink-gray-8">
                    {{ row.salesperson_name }}
                  </td>
                  <td class="px-4 py-3">
                    <router-link
                      :to="{ name: 'Lead', params: { leadId: row.lead } }"
                      class="font-medium text-ink-gray-9 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                    >
                      {{ row.company_name || row.lead }}
                    </router-link>
                    <p v-if="row.business" class="text-p-xs text-ink-gray-6">
                      {{ row.business }}
                    </p>
                  </td>
                  <td class="px-4 py-3">
                    <p class="text-ink-gray-8">
                      {{ row.contact_name }}
                      <span v-if="row.designation" class="text-ink-gray-6">
                        · {{ row.designation }}
                      </span>
                    </p>
                    <p
                      v-if="row.contact_number"
                      class="font-mono text-p-xs tabular-nums text-ink-gray-7"
                    >
                      {{ row.contact_number }}
                    </p>
                    <p
                      v-if="row.email"
                      class="break-all font-mono text-p-xs text-ink-gray-7"
                    >
                      {{ row.email }}
                    </p>
                  </td>
                  <td class="px-4 py-3 text-ink-gray-8">
                    {{ row.requirement_label }}
                  </td>
                  <td class="px-4 py-3">
                    <p class="text-ink-gray-8">
                      {{ row.quoted ? __("Yes") : __("No") }}
                    </p>
                    <template v-if="row.quoted">
                      <p class="tabular-nums text-ink-gray-8">
                        {{ amount(row) }}
                      </p>
                      <p class="font-mono text-p-xs text-ink-gray-6">
                        {{ row.quotation }}
                        <template v-if="row.quotation_count > 1">
                          {{
                            __("(latest of {0})", String(row.quotation_count))
                          }}
                        </template>
                      </p>
                    </template>
                  </td>
                  <td class="px-4 py-3">
                    <FormControl
                      type="select"
                      :model-value="row.conversion"
                      :aria-label="__('Conversion possibility')"
                      :options="conversionOptions"
                      @update:model-value="save(row, 'conversion', $event)"
                    />
                  </td>
                  <td class="px-4 py-3">
                    <input
                      type="number"
                      min="0"
                      :max="MAX_VISITS"
                      inputmode="numeric"
                      :value="row.visits"
                      :aria-label="__('Visits this week')"
                      class="h-7 w-16 rounded border-0 bg-surface-gray-2 px-2 text-p-sm tabular-nums text-ink-gray-8 focus:ring-2 focus:ring-highlight"
                      @change="saveVisits(row, $event)"
                    />
                  </td>
                  <td class="px-4 py-3">
                    <FormControl
                      type="select"
                      :model-value="row.follow_up"
                      :aria-label="__('Follow-up plan')"
                      :options="followUpOptions"
                      @update:model-value="save(row, 'follow_up', $event)"
                    />
                  </td>
                  <td class="px-4 py-3">
                    <textarea
                      :value="row.remarks"
                      rows="2"
                      maxlength="1000"
                      :aria-label="__('Remarks')"
                      :placeholder="__('What happened, what\'s next')"
                      class="w-full resize-y rounded border-0 bg-surface-gray-2 px-2 py-1.5 text-p-sm text-ink-gray-8 placeholder:text-ink-gray-5 focus:ring-2 focus:ring-highlight"
                      @change="saveRemarks(row, $event)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import MonthStepper from "@/pages/sales-targets/MonthStepper.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, createResource, FormControl, toast } from "frappe-ui";
import { useDebounceFn } from "@vueuse/core";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarCheck from "~icons/lucide/calendar-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import {
  CONVERSIONS,
  FOLLOW_UPS,
  MAX_VISITS,
  NOT_SET,
  optionsOf,
  REQUIREMENTS,
  WEEKLY_API,
  weekLabel,
  weekOptions,
  type SheetFields,
  type WeekData,
  type WeekRow,
} from "./weeklyLeadReport";

const route = useRoute();
const router = useRouter();

// the week, person and filters live in the URL, so a link opens the same report
const week = ref(String(route.query.week || ""));
const salesperson = ref(String(route.query.person || ""));
const FILTER_KEYS = [
  "search",
  "requirement",
  "conversion",
  "follow_up",
  "quoted",
] as const;
type FilterKey = typeof FILTER_KEYS[number];
const filters = reactive(
  Object.fromEntries(
    FILTER_KEYS.map((key) => [key, String(route.query[key] || "")])
  ) as Record<FilterKey, string>
);
const filtered = computed(() => FILTER_KEYS.some((key) => filters[key]));
// what the server and the Excel file are asked for, empty filters left out
const filterParams = () =>
  Object.fromEntries(
    FILTER_KEYS.filter((k) => filters[k]).map((k) => [k, filters[k]])
  );

/** A filter's options: any value first, then "Not set" where a field may be empty. */
function choicesOf(
  any: string,
  values: readonly (string | { value: string; label: string })[],
  withNotSet = true
) {
  const options = optionsOf(values).slice(1);
  return [
    { label: any, value: "" },
    ...options,
    ...(withNotSet ? [{ label: __("Not set"), value: NOT_SET }] : []),
  ];
}
const filterSelects: { key: FilterKey; label: string; options: any[] }[] = [
  {
    key: "requirement",
    label: __("Requirement"),
    options: choicesOf(__("Any requirement"), REQUIREMENTS),
  },
  {
    key: "conversion",
    label: __("Conversion possibility"),
    options: choicesOf(__("Any conversion"), CONVERSIONS),
  },
  {
    key: "follow_up",
    label: __("Follow-up plan"),
    options: choicesOf(__("Any follow-up plan"), FOLLOW_UPS),
  },
  {
    key: "quoted",
    label: __("Quoted"),
    options: choicesOf(__("Quoted or not"), ["Yes", "No"], false),
  },
];

function clearFilters() {
  for (const key of FILTER_KEYS) filters[key] = "";
}

const report = createResource({
  url: `${WEEKLY_API}.get_week`,
  makeParams: () => ({
    week: week.value || undefined,
    salesperson: salesperson.value || undefined,
    ...filterParams(),
  }),
  auto: true,
  onSuccess(data: WeekData) {
    // any day of the week reads it; the picker holds its Sunday
    if (week.value !== data.week_start) week.value = data.week_start;
  },
});
const data = computed(() => report.data as WeekData | undefined);

function keepInUrl() {
  router.replace({
    query: {
      week: week.value || undefined,
      person: salesperson.value || undefined,
      ...filterParams(),
    },
  });
}

watch([week, salesperson], ([, person], [oldWeek, oldPerson]) => {
  keepInUrl();
  // the first week is the server's answer, not a change to read again
  if (oldWeek || person !== oldPerson) report.reload();
});
// the selects read at once; typing in the search waits for a pause
watch(
  () => FILTER_KEYS.filter((k) => k !== "search").map((k) => filters[k]),
  () => {
    keepInUrl();
    report.reload();
  }
);
const searchSoon = useDebounceFn(() => {
  keepInUrl();
  report.reload();
}, 400);

const weeks = computed(() =>
  data.value ? weekOptions(data.value.this_week) : []
);
const personOptions = computed(() => [
  { label: __("Everyone"), value: "" },
  ...(data.value?.people || []).map((p) => ({
    label: p.full_name,
    value: p.user,
  })),
]);
const showPerson = computed(
  () => !!data.value?.sees_team && !salesperson.value
);

const summary = computed(() => {
  const rows = data.value?.rows || [];
  const visits = rows.reduce((sum, r) => sum + r.visits, 0);
  const quoted = rows.filter((r) => r.quoted).length;
  return __(
    "{0} leads · {1} visits · {2} quoted",
    String(rows.length),
    String(visits),
    String(quoted)
  );
});

const conversionOptions = optionsOf(CONVERSIONS);
const followUpOptions = optionsOf(FOLLOW_UPS);

function amount(row: WeekRow) {
  if (row.quoted_value == null) return "";
  return row.currency
    ? money(row.quoted_value, row.currency)
    : String(row.quoted_value);
}

/** Writes one of the lead's sheet fields on the ERP site; a failure puts it back. */
async function save<K extends keyof SheetFields>(
  row: WeekRow,
  field: K,
  value: SheetFields[K]
) {
  const before = row[field];
  if (before === value) return;
  row[field] = value;
  try {
    await call(`${WEEKLY_API}.update_lead`, {
      lead: row.lead,
      values: { [field]: value },
    });
  } catch (error) {
    row[field] = before;
    toast.error(errorText(error, __("Couldn't save that. Try again.")));
  }
}

function saveVisits(row: WeekRow, event: Event) {
  const input = event.target as HTMLInputElement;
  const visits = Math.trunc(Number(input.value || 0));
  if (!Number.isFinite(visits) || visits < 0 || visits > MAX_VISITS) {
    input.value = String(row.visits);
    toast.error(__("Visits this week go from 0 to {0}.", String(MAX_VISITS)));
    return;
  }
  save(row, "visits", visits);
}

function saveRemarks(row: WeekRow, event: Event) {
  save(row, "remarks", (event.target as HTMLTextAreaElement).value.trim());
}

function exportWeek() {
  // the file holds what the page shows: the same filters
  const query = new URLSearchParams({ week: week.value, ...filterParams() });
  if (salesperson.value) query.set("salesperson", salesperson.value);
  window.open(`/api/method/${WEEKLY_API}.export_week?${query}`, "_blank");
}
</script>
