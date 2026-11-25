<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Divisions')"
      :subtitle="
        __('Every division at a glance; open one for its own dashboard.')
      "
    >
      <template #right-header>
        <Button
          size="md"
          :aria-label="__('Refresh')"
          :loading="cards.loading"
          @click="cards.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          size="md"
          :label="__('Compare')"
          :route="{
            name: 'DivisionOverview',
            query: { ...route.query, division: '' },
          }"
        >
          <template #prefix>
            <LucideGlobe class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <!-- the period only: every division is on the page -->
        <DivisionFilters
          division=""
          v-model:period="period"
          v-model:custom="custom"
          :options="[]"
          :loading="cards.loading"
        />

        <TaskyState
          v-if="cards.error && !cards.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="noAccess ? LucideLock : LucideCircleAlert"
          :title="
            noAccess
              ? __('The divisions aren\'t for you')
              : __('Couldn\'t load the divisions')
          "
          :message="
            noAccess
              ? __(
                  'They are for Super Admins and the managers of a division. Ask a Super Admin if you need them.'
                )
              : errorText(cards.error, __('Try again in a minute.'))
          "
        >
          <Button
            v-if="!noAccess"
            :label="__('Try again')"
            @click="cards.reload()"
          />
        </TaskyState>

        <TaskyState
          v-else-if="!range"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideCalendarRange"
          :title="__('Pick both dates')"
          :message="__('Choose a from and a to date to see that period.')"
        />

        <div
          v-else-if="!cards.data"
          class="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div
            v-for="i in 3"
            :key="i"
            class="h-80 animate-pulse rounded-xl bg-surface-gray-3"
          />
        </div>

        <TaskyState
          v-else-if="!cards.data.cards.length"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideBuilding2"
          :title="__('No divisions yet')"
          :message="__('A Super Admin creates them in Settings → Divisions.')"
        />

        <template v-else>
          <p class="text-p-sm text-ink-gray-7" role="status">
            {{ summary }}
          </p>
          <div
            class="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3"
            :class="cards.loading ? 'opacity-60' : ''"
          >
            <DivisionCard
              v-for="card in cards.data.cards"
              :key="card.name"
              :card="card"
            />
          </div>
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
import { Button, createResource, usePageMeta } from "frappe-ui";
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideGlobe from "~icons/lucide/globe";
import LucideLock from "~icons/lucide/lock";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import DivisionCard from "./DivisionCard.vue";
import DivisionFilters from "./DivisionFilters.vue";
import { formatValue } from "./chartLook";
import { OVERVIEW_API, type DivisionCard as Card } from "./divisions";
import { useDivisionFilters } from "./useDivisionFilters";

usePageMeta(() => ({ title: __("Divisions") }));

const route = useRoute();
const { period, custom, range } = useDivisionFilters();

const cards = createResource<{ cards: Card[]; currency: string | null }>({
  url: `${OVERVIEW_API}.get_division_cards`,
  makeParams: () => ({ ...(range.value || {}) }),
});

watch(
  range,
  () => {
    if (range.value) cards.reload();
  },
  { immediate: true, deep: true }
);

const noAccess = computed(() => cards.error?.exc_type === "PermissionError");

const summary = computed(() => {
  const list = cards.data?.cards || [];
  const sum = (key: keyof Card) =>
    list.reduce((total, c) => total + (Number(c[key]) || 0), 0);
  const count = (v: number) => formatValue("count", v, null);
  return __(
    "{0} divisions · {1} people · {2} leads in the period · {3} open projects",
    count(list.length),
    count(sum("people")),
    count(sum("leads")),
    count(sum("active_projects"))
  );
});
</script>
