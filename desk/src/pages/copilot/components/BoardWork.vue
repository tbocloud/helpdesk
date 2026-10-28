<template>
  <div class="flex flex-col gap-4">
    <div
      class="grid grid-cols-1 items-end gap-3 sm:grid-cols-[minmax(12rem,18rem)_auto_auto]"
      role="group"
      :aria-label="__('Filter the work')"
    >
      <Link
        v-model="filters.customer"
        doctype="HD Customer"
        :label="__('Customer')"
        :placeholder="__('Every customer')"
      />
      <Switch v-model="filters.mine" :label="__('Only mine')" />
      <Switch
        v-model="filters.watch"
        :label="__('Raised by the error watch')"
      />
    </div>

    <p v-if="data" class="text-p-sm text-ink-gray-6">
      {{
        __(
          "{0} resolved this week. Each ticket shows its latest Copilot run; problems older than 30 days drop off.",
          String(data.resolved_this_week)
        )
      }}
    </p>

    <!-- one column per stage: side by side on a wide screen, one under another on a phone -->
    <div
      v-if="data"
      class="grid grid-cols-1 gap-3 lg:grid-flow-col lg:grid-cols-none lg:auto-cols-[minmax(15rem,1fr)] lg:overflow-x-auto lg:pb-2"
    >
      <SectionCard
        v-for="column in data.columns"
        :key="column.key"
        :title="column.label"
        :count="column.count"
      >
        <ul class="flex flex-col gap-2 px-3 pb-3">
          <li v-for="card in column.cards" :key="card.run">
            <a
              :href="card.url"
              class="block rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="font-mono text-sm tabular-nums text-ink-gray-6">
                  #{{ card.ticket }}
                </span>
                <span class="text-sm text-ink-gray-5" :title="__('Waited')">
                  {{ waited(card.waited_hours) }}
                </span>
              </div>
              <div class="mt-1 line-clamp-2 text-base text-ink-gray-9">
                {{ card.subject }}
              </div>
              <div class="mt-1 truncate text-sm text-ink-gray-6">
                {{ card.customer || "-" }}
                <template v-if="card.root_cause">
                  · {{ card.root_cause }}
                </template>
              </div>
              <div class="mt-1 flex flex-wrap items-center gap-1.5">
                <Badge :label="card.state" theme="gray" size="sm" />
                <Badge
                  v-if="card.source"
                  :label="__('Error watch')"
                  theme="orange"
                  size="sm"
                />
                <Badge
                  v-if="card.shadow"
                  :label="__('Shadow')"
                  theme="gray"
                  size="sm"
                />
              </div>
              <div class="mt-1 text-sm text-ink-gray-7">
                {{ __("Waits on {0}", card.waits_on) }}
              </div>
            </a>
          </li>
          <li
            v-if="!column.cards.length"
            class="px-1 py-2 text-sm text-ink-gray-5"
          >
            {{ __("Nothing here") }}
          </li>
          <li v-if="column.more" class="px-1 text-sm text-ink-gray-5">
            {{ __("and {0} more", String(column.more)) }}
          </li>
        </ul>
      </SectionCard>
    </div>
    <div
      v-else-if="work.loading"
      class="h-40 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
    />
    <ErrorMessage v-else-if="work.error" :message="errorText(work.error)" />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Badge, createResource, ErrorMessage, Switch } from "frappe-ui";
import { computed, reactive, watch } from "vue";
import {
  BOARD_API,
  useBoardRefresh,
  waited,
  type BoardColumn,
} from "../boardMeta";

const filters = reactive({ customer: "", mine: false, watch: false });

const work = createResource({
  url: `${BOARD_API}.work`,
  makeParams: () => ({
    customer: filters.customer || undefined,
    mine: filters.mine ? 1 : 0,
    source: filters.watch ? "Error watch" : undefined,
  }),
  auto: true,
});
watch(filters, () => work.reload());
useBoardRefresh(work);

const data = computed(
  () =>
    work.data as
      | { columns: BoardColumn[]; resolved_this_week: number }
      | undefined
);
</script>
