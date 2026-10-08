<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">
          {{ __("Support hours") }}
        </h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="list.loading && !!list.data"
          :aria-label="__('Refresh')"
          @click="list.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          variant="solid"
          :label="__('Download CSV')"
          :tooltip="__('The contracts below as a spreadsheet, for billing')"
          @click="download"
        >
          <template #prefix>
            <LucideFileSpreadsheet class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <p class="max-w-2xl text-p-sm text-ink-gray-6">
          {{
            __(
              "Every support contract running today and how much of this period's hours are used, most used first. Only billable time counts."
            )
          }}
        </p>

        <TaskyState
          v-if="list.error && !list.data"
          class="mt-5"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the support hours')"
          :message="
            errorText(list.error, __('Check your connection and try again.'))
          "
          error
        >
          <Button :label="__('Retry')" @click="list.reload()" />
        </TaskyState>

        <template v-else>
          <section
            :aria-label="__('Contracts by how much is used')"
            class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3"
          >
            <StatTile
              compact
              :label="__('Running today')"
              :value="data ? data.total : '–'"
              :icon="LucideHourglass"
              :loading="loading"
              :pressed="!stage"
              @click="stage = ''"
            />
            <StatTile
              compact
              :label="__('Running low')"
              :value="data ? data.counts.warning : '–'"
              :sub="__('At or past the alert level')"
              :icon="LucideTriangleAlert"
              :icon-tone="data?.counts.warning ? 'warning' : 'neutral'"
              :loading="loading"
              :pressed="stage === 'warning'"
              @click="stage = stage === 'warning' ? '' : 'warning'"
            />
            <StatTile
              compact
              :label="__('Used up')"
              :value="data ? data.counts.over : '–'"
              :sub="__('Extra hours to bill')"
              :icon="LucideCircleAlert"
              :icon-tone="data?.counts.over ? 'danger' : 'neutral'"
              :value-tone="data?.counts.over ? 'danger' : 'neutral'"
              :loading="loading"
              :pressed="stage === 'over'"
              @click="stage = stage === 'over' ? '' : 'over'"
            />
          </section>

          <div class="mt-4 flex flex-wrap items-end gap-3">
            <div class="w-full sm:w-52">
              <FormControl
                v-model="contractType"
                type="select"
                :label="__('Type')"
                :options="typeOptions"
              />
            </div>
          </div>

          <SectionCard
            class="mt-4 overflow-hidden"
            :title="__('Contracts')"
            :count="loading ? undefined : rows.length"
            :aria-busy="list.loading"
          >
            <div v-if="loading" :aria-label="__('Loading')">
              <div
                v-for="i in 5"
                :key="i"
                class="flex items-center gap-4 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
              >
                <span
                  class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2"
                />
                <span
                  class="ml-auto h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
            </div>

            <TaskyState
              v-else-if="!rows.length && (stage || contractType)"
              :icon="LucideSearchX"
              :title="__('No contracts match')"
              :message="__('No running contract fits these filters.')"
            >
              <Button :label="__('Show all contracts')" @click="clearFilters" />
            </TaskyState>
            <TaskyState
              v-else-if="!rows.length"
              :icon="LucideHourglass"
              :title="__('No support contracts running')"
              :message="
                __(
                  'Add a customer\'s AMC or block of hours from the Support hours tab on their page.'
                )
              "
            >
              <Button
                :label="__('Open customers')"
                @click="router.push({ name: 'CustomerList' })"
              />
            </TaskyState>

            <template v-else>
              <table
                class="hidden w-full text-sm md:table"
                :class="list.loading ? 'opacity-60' : ''"
              >
                <caption class="sr-only">
                  {{
                    __("Support contracts running today")
                  }}
                </caption>
                <thead>
                  <tr
                    class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs text-ink-gray-5"
                  >
                    <th scope="col" class="px-4 py-2 font-normal">
                      {{ __("Customer") }}
                    </th>
                    <th scope="col" class="px-3 py-2 font-normal">
                      {{ __("Current period") }}
                    </th>
                    <th scope="col" class="w-1/5 px-3 py-2 font-normal">
                      <span class="sr-only">{{ __("Share used") }}</span>
                    </th>
                    <th scope="col" class="px-3 py-2 text-right font-normal">
                      {{ __("Used") }}
                    </th>
                    <th scope="col" class="px-3 py-2 text-right font-normal">
                      {{ __("Hours") }}
                    </th>
                    <th scope="col" class="px-4 py-2 text-right font-normal">
                      {{ __("Left") }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in rows"
                    :key="row.name"
                    class="border-b border-outline-gray-1 last:border-b-0"
                  >
                    <th
                      scope="row"
                      class="max-w-[16rem] px-4 py-2.5 text-left font-normal"
                    >
                      <RouterLink
                        :to="customerLink(row)"
                        class="block truncate rounded text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      >
                        {{ row.customer }}
                      </RouterLink>
                      <span class="block truncate text-xs text-ink-gray-5">
                        {{ row.contract_name }} · {{ __(row.contract_type) }}
                      </span>
                    </th>
                    <td class="px-3 py-2.5 tabular-nums text-ink-gray-7">
                      {{ periodText(row) }}
                    </td>
                    <td class="px-3 py-2.5">
                      <SupportHoursMeter :period="row" :label="row.customer" />
                    </td>
                    <td
                      class="px-3 py-2.5 text-right font-mono tabular-nums"
                      :class="INK[STAGE_TONE[row.stage]]"
                    >
                      <span class="inline-flex items-center justify-end gap-1">
                        <component
                          :is="STAGE_ICON[row.stage]"
                          v-if="STAGE_ICON[row.stage]"
                          class="size-3.5"
                          aria-hidden="true"
                        />
                        {{ row.percent }}%
                      </span>
                      <span class="sr-only">{{ STAGE_LABEL[row.stage] }}</span>
                    </td>
                    <td
                      class="px-3 py-2.5 text-right font-mono tabular-nums text-ink-gray-8"
                    >
                      {{ hours(row.used) }} / {{ hours(row.allowance) }}
                    </td>
                    <td
                      class="px-4 py-2.5 text-right font-mono tabular-nums"
                      :class="
                        row.remaining < 0 ? 'text-danger' : 'text-ink-gray-8'
                      "
                    >
                      {{
                        row.remaining < 0
                          ? __("{0} over", hours(-row.remaining))
                          : hours(row.remaining)
                      }}
                    </td>
                  </tr>
                </tbody>
              </table>

              <!-- small screens: a two-line row per contract -->
              <ul role="list" class="md:hidden">
                <li
                  v-for="row in rows"
                  :key="row.name"
                  class="flex flex-col gap-1.5 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                >
                  <div class="flex items-baseline justify-between gap-3">
                    <RouterLink
                      :to="customerLink(row)"
                      class="min-w-0 truncate rounded text-sm text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    >
                      {{ row.customer }}
                    </RouterLink>
                    <span
                      class="inline-flex shrink-0 items-center gap-1 font-mono text-sm tabular-nums"
                      :class="INK[STAGE_TONE[row.stage]]"
                    >
                      <component
                        :is="STAGE_ICON[row.stage]"
                        v-if="STAGE_ICON[row.stage]"
                        class="size-3.5"
                        aria-hidden="true"
                      />
                      {{ row.percent }}%
                    </span>
                  </div>
                  <SupportHoursMeter :period="row" :label="row.customer" />
                  <span class="text-xs tabular-nums text-ink-gray-6">
                    {{ usageText(row) }} · {{ periodText(row) }}
                  </span>
                </li>
              </ul>
            </template>
          </SectionCard>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import SupportHoursMeter from "@/components/customer/SupportHoursMeter.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { INK } from "@/components/tone";
import {
  CONTRACT_TYPES,
  hours,
  periodText,
  STAGE_ICON,
  STAGE_LABEL,
  STAGE_TONE,
  usageText,
  type SupportContract,
  type UsagePeriod,
  type UsageStage,
} from "@/composables/supportHours";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearchX from "~icons/lucide/search-x";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";

type Row = UsagePeriod &
  Pick<
    SupportContract,
    "name" | "contract_name" | "contract_type" | "customer" | "billing_period"
  >;

interface SupportHoursList {
  rows: Row[];
  total: number;
  counts: Record<Exclude<UsageStage, "ok">, number>;
}

const route = useRoute();
const router = useRouter();

function queryValue(key: string, allowed: readonly string[]) {
  const value = route.query[key];
  return typeof value === "string" && allowed.includes(value) ? value : "";
}

// filters live in the URL, so a filtered list can be shared
const stage = ref(queryValue("stage", ["warning", "over"]));
const contractType = ref(queryValue("type", CONTRACT_TYPES));

const typeOptions = [
  { label: __("All types"), value: "" },
  ...CONTRACT_TYPES.map((t) => ({ label: __(t), value: t })),
];

const list = createResource({
  url: "helpdesk.api.support_contracts.get_support_hours",
  makeParams: () => ({
    stage: stage.value || undefined,
    contract_type: contractType.value || undefined,
  }),
  auto: true,
});

watch([stage, contractType], () => {
  router.replace({
    query: {
      ...route.query,
      stage: stage.value || undefined,
      type: contractType.value || undefined,
    },
  });
  list.reload();
});

const data = computed<SupportHoursList | null>(() => list.data ?? null);
const rows = computed(() => data.value?.rows ?? []);
const loading = computed(() => list.loading && !list.data);

function clearFilters() {
  stage.value = "";
  contractType.value = "";
}

function customerLink(row: Row) {
  return {
    name: "Customer",
    params: { id: row.customer },
    hash: "#support-hours",
  };
}

function download() {
  const params = new URLSearchParams();
  if (stage.value) params.set("stage", stage.value);
  if (contractType.value) params.set("contract_type", contractType.value);
  window.open(
    `/api/method/helpdesk.api.support_contracts.download_support_hours?${params}`,
    "_blank"
  );
}
</script>
