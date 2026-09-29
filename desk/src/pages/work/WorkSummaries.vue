<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Weekly summaries") }}
        </div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="summaries.loading"
          :aria-label="__('Refresh')"
          @click="summaries.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          variant="solid"
          :label="__('Generate now')"
          @click="showGenerate = true"
        >
          <template #prefix>
            <LucideSparkles class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <p class="max-w-xl text-p-sm text-ink-gray-6">
            {{
              __(
                "Every Monday each active customer gets a summary of the previous week's tickets, tasks and project progress."
              )
            }}
          </p>
          <div class="w-full sm:w-64">
            <Link
              v-model="customer"
              doctype="HD Customer"
              :label="__('Customer')"
              :placeholder="__('All customers')"
            />
          </div>
        </div>

        <TaskyState
          v-if="summaries.error && !summaries.data"
          class="mt-3"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load summaries')"
          :message="loadError"
          error
        >
          <Button :label="__('Retry')" @click="summaries.reload()" />
        </TaskyState>

        <div
          v-else
          class="mt-3 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
        >
          <div
            class="hidden grid-cols-[1fr_11rem_5rem_7rem] gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
            aria-hidden="true"
          >
            <span>{{ __("Customer") }}</span>
            <span>{{ __("Period") }}</span>
            <span>{{ __("Written") }}</span>
            <span class="text-right">{{ __("Generated") }}</span>
          </div>

          <div
            v-if="summaries.loading && !summaries.data"
            :aria-label="__('Loading')"
            aria-busy="true"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
            >
              <div class="flex flex-1 flex-col gap-2 md:flex-row md:gap-4">
                <div
                  class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
              <div
                class="hidden h-3 w-16 animate-pulse rounded bg-surface-gray-2 md:block"
              />
            </div>
          </div>

          <TaskyState
            v-else-if="!items.length"
            :icon="LucideNewspaper"
            :title="
              customer
                ? __('No summaries for this customer yet')
                : __('No summaries yet')
            "
            :message="
              __(
                'Summaries of customers whose projects you run show up here after the Monday run, or when you generate one.'
              )
            "
          >
            <Button
              v-if="customer"
              :label="__('Show all customers')"
              @click="customer = ''"
            />
          </TaskyState>

          <ul v-else role="list">
            <li
              v-for="item in items"
              :key="item.name"
              class="border-b border-outline-gray-1 last:border-b-0"
            >
              <RouterLink
                :to="{ name: 'WorkSummary', params: { name: item.name } }"
                class="flex flex-col gap-1.5 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 md:grid md:grid-cols-[1fr_11rem_5rem_7rem] md:items-center md:gap-4"
              >
                <span class="truncate text-base-medium text-ink-gray-8">
                  {{ item.customer }}
                </span>
                <span class="flex flex-wrap items-center gap-2 md:contents">
                  <span class="font-mono text-sm tabular-nums text-ink-gray-7">
                    {{ formatPeriod(item.period_start, item.period_end) }}
                  </span>
                  <span>
                    <SummaryKindBadge :ai="!!item.generated_by_ai" />
                  </span>
                  <span
                    class="font-mono text-xs tabular-nums text-ink-gray-5 md:text-right"
                    :title="dayjs(item.creation).format('D MMM YYYY, HH:mm')"
                  >
                    {{ formatDay(item.creation) }}
                  </span>
                </span>
              </RouterLink>
            </li>
          </ul>
        </div>

        <div v-if="canLoadMore" class="mt-3 flex justify-center">
          <Button
            :label="__('Load more')"
            :loading="summaries.loading"
            @click="limit += PAGE_SIZE"
          />
        </div>
      </div>
    </div>

    <GenerateSummaryDialog
      v-model:open="showGenerate"
      :default-customer="customer"
      @generated="openSummary"
    />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/pages/tasky/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideNewspaper from "~icons/lucide/newspaper";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSparkles from "~icons/lucide/sparkles";
import GenerateSummaryDialog from "./components/GenerateSummaryDialog.vue";
import SummaryKindBadge from "./components/SummaryKindBadge.vue";
import {
  errorText,
  formatDay,
  formatPeriod,
  type SummaryDetail,
  type SummaryListItem,
} from "./summaryMeta";

const PAGE_SIZE = 20;
// the server caps a page at 100
const MAX_LIMIT = 100;

const route = useRoute();
const router = useRouter();

const customer = ref(
  typeof route.query.customer === "string" ? route.query.customer : ""
);
const limit = ref(PAGE_SIZE);
const showGenerate = ref(false);

const summaries = createResource({
  url: "helpdesk.api.work_summary.get_summaries",
  makeParams: () => ({
    customer: customer.value || undefined,
    limit: limit.value,
  }),
  auto: true,
});

// keep the filter in the URL so it survives reloads and can be shared
watch(customer, (value) => {
  router.replace({ query: { ...route.query, customer: value || undefined } });
  limit.value = PAGE_SIZE;
  summaries.reload();
});

watch(limit, (value, previous) => {
  if (value > previous) summaries.reload();
});

const items = computed<SummaryListItem[]>(
  () => (summaries.data as SummaryListItem[] | undefined) ?? []
);

const canLoadMore = computed(
  () => items.value.length >= limit.value && limit.value < MAX_LIMIT
);

const loadError = computed(() =>
  errorText(summaries.error, __("Check your connection and try again."))
);

function openSummary(summary: SummaryDetail) {
  router.push({ name: "WorkSummary", params: { name: summary.name } });
}
</script>
