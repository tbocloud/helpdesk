<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Home") }}</div>
      </template>
      <template #right-header>
        <!-- one tap from Home on the phone (docs/lead-bank.md) -->
        <Button
          v-if="canUseLeadBank"
          variant="solid"
          :label="__('Add a lead')"
          :route="{ name: 'LeadBankAdd' }"
        >
          <template #prefix>
            <LucideCamera class="size-4" aria-hidden="true" />
          </template>
        </Button>
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
        <!-- greeting, date and the few things that need a look today -->
        <header class="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div class="flex min-w-0 flex-1 basis-80 flex-col gap-1">
            <h1 class="text-2xl font-semibold text-ink-gray-9">
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
              <span
                v-if="onLeaveToday"
                class="inline-flex items-center gap-1.5"
              >
                <LucideTreePalm
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                {{ onLeaveToday }}
              </span>
            </p>
            <p
              v-if="data && !parts.length"
              role="status"
              class="mt-1 inline-flex items-center gap-1.5 text-p-base text-success"
            >
              <!-- only when nothing is open: held, undated and later work all count -->
              <LucideCircleCheck class="size-4" aria-hidden="true" />
              {{ __("All clear. You have no open work.") }}
            </p>
            <span
              v-else-if="!data && home.loading"
              class="mt-1 h-5 w-72 max-w-full animate-pulse rounded bg-surface-gray-2"
            />
          </div>
          <ul
            v-if="pills.length"
            role="list"
            class="flex flex-wrap gap-2"
            :aria-label="__('Needs a look today')"
          >
            <li v-for="pill in pills" :key="pill.key">
              <RouterLink
                v-if="pill.to"
                :to="pill.to"
                class="inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-medium tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                :class="TONE_CLASSES[pill.tone]"
              >
                <span
                  class="size-1.5 rounded-full bg-current"
                  aria-hidden="true"
                />
                {{ pill.label }}
              </RouterLink>
              <span
                v-else
                class="inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-medium tabular-nums"
                :class="TONE_CLASSES[pill.tone]"
              >
                <span
                  class="size-1.5 rounded-full bg-current"
                  aria-hidden="true"
                />
                {{ pill.label }}
              </span>
            </li>
          </ul>
        </header>

        <FollowUpStrip v-if="data" :summary="data.follow_ups" />

        <StandupCard v-if="data?.standup" :standup="data.standup" />

        <AIProviderBanner
          v-if="data?.systems?.ai.providers"
          :status="data.systems.ai.providers"
        >
          <!-- Settings open from the desktop layout only -->
          <Button
            v-if="!isMobileView"
            :label="__('Open AI providers')"
            @click="openAIProviders"
          />
        </AIProviderBanner>

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
          <HomeNumbers :day="data.day" :company="data.company" />

          <PulseStrip v-if="data.company" :company="data.company" />

          <div
            class="grid grid-cols-1 gap-5"
            :class="hasSide ? 'xl:grid-cols-[minmax(0,1fr)_20rem]' : ''"
          >
            <div class="flex min-w-0 flex-col gap-5">
              <DoNext
                v-if="doNext.length"
                :items="doNext"
                @changed="home.reload()"
              />
              <ActionPlan :day="data.day" />
              <YourDay
                :day="data.day"
                :hide="doNextKeys"
                @changed="home.reload()"
              />
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
import AIProviderBanner from "@/components/AIProviderBanner.vue";
import FollowUpStrip from "@/components/FollowUpStrip.vue";
import {
  setActiveSettingsTab,
  showSettingsModal,
} from "@/components/Settings/settingsModal";
import { TONE_CLASSES, type Tone } from "@/components/tone";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useScreenSize } from "@/composables/screen";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed } from "vue";
import LucideCamera from "~icons/lucide/camera";
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
import StandupCard from "./components/StandupCard.vue";
import SystemsCard from "./components/SystemsCard.vue";
import YourDay from "./components/YourDay.vue";
import YourProjects from "./components/YourProjects.vue";
import DoNext from "./components/DoNext.vue";
import HomeNumbers from "./components/HomeNumbers.vue";
import {
  countLabel,
  greeting,
  statusParts,
  ticketLinks,
  type DayTask,
  type HomeData,
} from "./homeMeta";
import { itemKey } from "@/pages/work/workMeta";
import type { RouteLocationRaw } from "vue-router";

const { userFirstName, canUseLeadBank } = storeToRefs(useAuthStore());

const home = createResource({
  url: "helpdesk.api.home.get_home",
  auto: true,
});

const data = computed<HomeData | null>(() => home.data ?? null);
const parts = computed(() => (data.value ? statusParts(data.value.day) : []));

interface Pill {
  key: string;
  label: string;
  tone: Tone;
  to?: RouteLocationRaw;
}

// what needs a look today: the user's own late and due work, waiting replies and
// reviews, and (for people who see the company) tickets past their SLA
const pills = computed<Pill[]>(() => {
  const d = data.value;
  if (!d) return [];
  const own: Record<string, Pick<Pill, "tone" | "to">> = {
    overdue: {
      tone: "danger",
      to: { name: "MyWork", query: { tab: "overdue" } },
    },
    due_today: { tone: "warning", to: { name: "MyWork" } },
    replies: { tone: "info", to: { name: "MyWork", query: { tab: "ticket" } } },
    approvals: { tone: "neutral" },
  };
  const list: Pill[] = statusParts(d.day)
    .filter((part) => part.key in own)
    .map((part) => ({ key: part.key, label: part.label, ...own[part.key] }));
  const sla = d.company?.tickets.sla_breached ?? 0;
  if (sla)
    list.push({
      key: "sla",
      label: countLabel(
        sla,
        __("1 ticket past SLA"),
        __("{0} tickets past SLA")
      ),
      tone: "danger",
      to: ticketLinks.slaBreached(),
    });
  return list;
});

// "Do next": the most urgent of what the day already lists, one row each
const DO_NEXT_LIMIT = 5;
const doNext = computed<DayTask[]>(() => {
  const day = data.value?.day;
  if (!day) return [];
  const seen = new Set<string>();
  return [
    ...day.close_first.items,
    ...day.replies.items,
    ...day.approvals.items,
    ...day.in_progress.items,
  ]
    .filter((item) => {
      const key = itemKey(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, DO_NEXT_LIMIT) as DayTask[];
});
const doNextKeys = computed(() => new Set(doNext.value.map(itemKey)));

const hasSide = computed(
  () => !!data.value?.company || !!data.value?.day.projects.count
);

const { isMobileView } = useScreenSize();

function openAIProviders() {
  setActiveSettingsTab("AI providers");
  showSettingsModal.value = true;
}

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
