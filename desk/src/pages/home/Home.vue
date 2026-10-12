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
            v-if="nextHoliday || onLeaveToday"
            class="flex flex-wrap items-center gap-x-4 gap-y-1 text-p-sm text-ink-gray-6"
          >
            <RouterLink
              v-if="nextHoliday"
              :to="{ name: 'WorkCalendar' }"
              class="inline-flex items-center gap-1.5 rounded hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <LucideCalendarOff
                class="size-4 shrink-0 text-info"
                aria-hidden="true"
              />
              {{ nextHoliday }}
            </RouterLink>
            <span v-if="onLeaveToday" class="inline-flex items-center gap-1.5">
              <LucideTreePalm
                class="size-4 shrink-0 text-ink-gray-5"
                aria-hidden="true"
              />
              {{ onLeaveToday }}
            </span>
          </p>
          <p
            v-if="data"
            role="status"
            class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-p-base"
          >
            <!-- only when nothing is open: held, undated and later work all count -->
            <span
              v-if="!parts.length"
              class="inline-flex items-center gap-1.5 text-success"
            >
              <LucideCircleCheck class="size-4" aria-hidden="true" />
              {{ __("All clear. You have no open work.") }}
            </span>
            <template v-for="(part, index) in parts" :key="part.key">
              <span v-if="index" class="text-ink-gray-4" aria-hidden="true"
                >·</span
              >
              <span
                class="inline-flex items-center gap-1.5 tabular-nums"
                :class="INK[part.tone]"
              >
                <component :is="part.icon" class="size-4" aria-hidden="true" />
                {{ part.label }}
              </span>
            </template>
          </p>
          <span
            v-else-if="home.loading"
            class="mt-1 h-5 w-72 max-w-full animate-pulse rounded bg-surface-gray-2"
          />
        </header>

        <FollowUpStrip v-if="data" :summary="data.follow_ups" />

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
              <ActionPlan :day="data.day" />
              <YourDay :day="data.day" @changed="home.reload()" />
              <NeedsAttention
                v-if="data.company"
                :groups="data.company.attention_groups"
                @changed="home.reload()"
              />
              <!-- in the main column, under the attention list, so the side stays short -->
              <SystemsCard v-if="data.systems" :systems="data.systems" />
            </div>
            <aside
              v-if="hasSide"
              class="flex min-w-0 flex-col gap-5"
              :aria-label="__('Your projects, customers and team')"
            >
              <YourProjects
                v-if="data.day.projects.count"
                :projects="data.day.projects"
              />
              <HomeSide v-if="data.company" :company="data.company" />
            </aside>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import FollowUpStrip from "@/components/FollowUpStrip.vue";
import { INK } from "@/components/tone";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCalendarOff from "~icons/lucide/calendar-off";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTreePalm from "~icons/lucide/tree-palm";
import { RouterLink } from "vue-router";
import ActionPlan from "./components/ActionPlan.vue";
import HomeSide from "./components/HomeSide.vue";
import NeedsAttention from "./components/NeedsAttention.vue";
import PulseStrip from "./components/PulseStrip.vue";
import SystemsCard from "./components/SystemsCard.vue";
import YourDay from "./components/YourDay.vue";
import YourProjects from "./components/YourProjects.vue";
import { greeting, statusParts, type HomeData } from "./homeMeta";

const { userFirstName } = storeToRefs(useAuthStore());

const home = createResource({
  url: "helpdesk.api.home.get_home",
  auto: true,
});

const data = computed<HomeData | null>(() => home.data ?? null);
const parts = computed(() => (data.value ? statusParts(data.value.day) : []));
const hasSide = computed(
  () => !!data.value?.company || !!data.value?.day.projects.count
);

const todayLabel = computed(() => dayjs().format("dddd, D MMMM YYYY"));

// "Next holiday: Diwali · Thu 20 Oct", from the hub's holiday list
const nextHoliday = computed(() => {
  const holiday = data.value?.calendar?.next_holiday;
  if (!holiday) return "";
  const day = dayjs(holiday.date);
  return day.isSame(dayjs(), "day")
    ? __("Today is a holiday: {0}", holiday.description)
    : __(
        "Next holiday: {0} · {1}",
        holiday.description,
        day.format("ddd D MMM")
      );
});

// for people who run work: "On leave today: Anu Varghese (until Wed 14 Oct), …"
const onLeaveToday = computed(() => {
  const people = data.value?.calendar?.on_leave_today;
  if (!people?.length) return "";
  const span = (p: typeof people[number]) =>
    p.half_day
      ? __("half day")
      : dayjs(p.to_date).isSame(dayjs(), "day")
      ? __("back tomorrow")
      : __("until {0}", dayjs(p.to_date).format("ddd D MMM"));
  return __(
    "On leave today: {0}",
    people.map((p) => `${p.full_name} (${span(p)})`).join(", ")
  );
});
</script>
