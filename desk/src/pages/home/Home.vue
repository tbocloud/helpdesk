<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Home") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="home.loading"
          :aria-label="__('Refresh')"
          @click="home.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div
        class="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-5 md:px-6"
      >
        <!-- greeting and the one-line status -->
        <header class="flex flex-col gap-1">
          <h1 class="text-xl-semibold text-ink-gray-9">
            {{ greeting(userFirstName || "") }}
          </h1>
          <p class="text-p-sm text-ink-gray-6">{{ todayLabel }}</p>
          <p
            v-if="data"
            role="status"
            class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-p-base"
          >
            <template v-if="!parts.length">
              <span class="inline-flex items-center gap-1.5 text-success">
                <LucideCircleCheck class="size-4" aria-hidden="true" />
                {{ __("All clear. Nothing needs action right now.") }}
              </span>
            </template>
            <template v-else>
              <span
                v-if="clearOnTickets"
                class="inline-flex items-center gap-1.5 text-ink-gray-7"
              >
                <LucideCircleCheck
                  class="size-4 text-success"
                  aria-hidden="true"
                />
                {{ __("All clear on tickets") }}
              </span>
              <template v-for="(part, index) in parts" :key="part.key">
                <span
                  v-if="index || clearOnTickets"
                  class="text-ink-gray-4"
                  aria-hidden="true"
                  >·</span
                >
                <span
                  class="inline-flex items-center gap-1.5"
                  :class="STATUS_TEXT[part.tone]"
                >
                  <component
                    :is="STATUS_ICON[part.tone]"
                    v-if="STATUS_ICON[part.tone]"
                    class="size-4"
                    aria-hidden="true"
                  />
                  {{ part.label }}
                </span>
              </template>
            </template>
          </p>
          <span
            v-else-if="home.loading"
            class="mt-1 h-5 w-72 max-w-full animate-pulse rounded bg-surface-gray-2"
          />
        </header>

        <TaskyState
          v-if="home.error && !data"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the dashboard')"
          :message="__('Check your connection and try again.')"
          error
        >
          <Button :label="__('Retry')" @click="home.reload()" />
        </TaskyState>

        <div v-else-if="!data" class="flex flex-col gap-5" aria-hidden="true">
          <div class="h-9 w-full animate-pulse rounded-md bg-surface-gray-2" />
          <div class="h-48 w-full animate-pulse rounded-lg bg-surface-gray-2" />
        </div>

        <template v-else>
          <PulseStrip v-if="data.company" :company="data.company" />

          <div
            class="grid grid-cols-1 gap-5"
            :class="hasSide ? 'xl:grid-cols-[minmax(0,1fr)_20rem]' : ''"
          >
            <div class="flex min-w-0 flex-col gap-5">
              <YourDay :day="data.day" @changed="home.reload()" />
              <NeedsAttention
                v-if="data.company"
                :groups="data.company.attention_groups"
                @changed="home.reload()"
              />
            </div>
            <aside
              v-if="hasSide"
              class="flex min-w-0 flex-col gap-5"
              :aria-label="__('Customers, projects and team')"
            >
              <HomeSide v-if="data.company" :company="data.company" />
              <SystemsCard v-if="data.systems" :systems="data.systems" />
            </aside>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/pages/tasky/components/TaskyState.vue";
import type { Tone } from "@/pages/tasky/taskMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, type Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import HomeSide from "./components/HomeSide.vue";
import NeedsAttention from "./components/NeedsAttention.vue";
import PulseStrip from "./components/PulseStrip.vue";
import SystemsCard from "./components/SystemsCard.vue";
import YourDay from "./components/YourDay.vue";
import { greeting, statusParts, ticketsClear, type HomeData } from "./homeMeta";

// full class strings so Tailwind's scanner keeps them
const STATUS_TEXT: Record<Tone, string> = {
  neutral: "text-ink-gray-8",
  info: "text-info",
  warning: "text-warning",
  success: "text-success",
  danger: "text-danger",
};

const STATUS_ICON: Partial<Record<Tone, Component>> = {
  warning: LucideCircleAlert,
  danger: LucideTriangleAlert,
};

const { userFirstName } = storeToRefs(useAuthStore());

const home = createResource({
  url: "helpdesk.api.home.get_home",
  auto: true,
});

const data = computed<HomeData | null>(() => home.data ?? null);
const parts = computed(() => (data.value ? statusParts(data.value) : []));
const clearOnTickets = computed(() => !!data.value && ticketsClear(data.value));
const hasSide = computed(() => !!(data.value?.company || data.value?.systems));

const todayLabel = computed(() => dayjs().format("dddd, D MMMM YYYY"));
</script>
