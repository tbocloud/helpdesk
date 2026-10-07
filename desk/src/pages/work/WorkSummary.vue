<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <RouterLink
          :to="{ name: 'WorkSummaries' }"
          class="flex shrink-0 items-center gap-1 rounded text-lg-medium text-ink-gray-5 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <LucideArrowLeft class="size-4 md:hidden" aria-hidden="true" />
          <span class="sr-only md:not-sr-only">{{
            __("Weekly summaries")
          }}</span>
        </RouterLink>
        <LucideChevronRight
          class="hidden size-4 shrink-0 text-ink-gray-4 md:block"
          aria-hidden="true"
        />
        <div class="truncate text-lg-medium text-ink-gray-9">
          {{ detail?.customer || __("Summary") }}
        </div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="summary.loading"
          :aria-label="__('Refresh')"
          @click="summary.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="summary.error && !detail"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load this summary')"
          :message="loadError"
          error
        >
          <Button :label="__('Retry')" @click="summary.reload()" />
          <Button
            :label="__('All summaries')"
            @click="router.push({ name: 'WorkSummaries' })"
          />
        </TaskyState>

        <div
          v-else-if="!detail"
          class="flex flex-col gap-5"
          :aria-label="__('Loading')"
          aria-busy="true"
        >
          <div class="flex flex-col gap-2">
            <div class="h-5 w-1/3 animate-pulse rounded bg-surface-gray-2" />
            <div class="h-3.5 w-40 animate-pulse rounded bg-surface-gray-2" />
          </div>
          <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <div
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-5"
            >
              <div
                v-for="i in 7"
                :key="i"
                class="h-3.5 animate-pulse rounded bg-surface-gray-2"
                :class="i % 3 === 0 ? 'w-1/4' : 'w-full'"
              />
            </div>
            <div
              class="h-64 animate-pulse rounded-lg border border-outline-gray-2 bg-surface-gray-1"
            />
          </div>
        </div>

        <template v-else>
          <header class="flex flex-col gap-1.5">
            <h1 class="text-xl font-semibold text-ink-gray-9">
              {{ detail.customer }}
            </h1>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono text-sm tabular-nums text-ink-gray-7">
                {{ formatPeriod(detail.period_start, detail.period_end) }}
              </span>
              <SummaryKindBadge :ai="!!detail.generated_by_ai" />
              <span
                class="font-mono text-xs tabular-nums text-ink-gray-5"
                :title="dayjs(detail.creation).format('D MMM YYYY, HH:mm')"
              >
                {{ __("Generated {0}", formatDay(detail.creation)) }}
              </span>
            </div>
          </header>

          <div class="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <section
              class="rounded-lg border border-outline-gray-2 bg-surface-base p-4 md:p-5"
              :aria-label="__('Summary')"
            >
              <!-- the server builds this from escaped text with only
                   p/ul/li/strong tags, so it is safe to render as HTML -->
              <div
                v-if="detail.summary"
                class="text-p-base text-ink-gray-8 [&>*:first-child]:mt-0 [&_li]:pl-1 [&_li]:marker:text-ink-gray-4 [&_p]:my-2 [&_strong]:font-semibold [&_strong]:text-ink-gray-9 [&_ul]:mb-4 [&_ul]:mt-1 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5"
                v-html="detail.summary"
              />
              <p v-else class="text-p-sm text-ink-gray-5">
                {{ __("This summary has no text.") }}
              </p>
            </section>

            <SummaryStatsPanel :stats="detail.stats" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, watch } from "vue";
import { useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import SummaryKindBadge from "./components/SummaryKindBadge.vue";
import SummaryStatsPanel from "./components/SummaryStatsPanel.vue";
import { formatDay, formatPeriod, type SummaryDetail } from "./summaryMeta";

const props = defineProps<{ name: string }>();

const router = useRouter();

const summary = createResource({
  url: "helpdesk.api.work_summary.get_summary",
  makeParams: () => ({ name: props.name }),
  auto: true,
});

// the same page is reused when following a link to another summary
watch(
  () => props.name,
  () => {
    summary.reset();
    summary.reload();
  }
);

const detail = computed(() => summary.data as SummaryDetail | undefined | null);

const loadError = computed(() =>
  errorText(
    summary.error,
    __("It may have been removed, or you may not have access to it.")
  )
);
</script>
