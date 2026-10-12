<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <header
        class="flex w-full items-center justify-between gap-3 px-4 py-2.5 md:px-6 md:py-3"
      >
        <h1 class="min-w-0 truncate text-3xl font-semibold text-ink-gray-9">
          {{ __("Content Calendar") }}
        </h1>
        <div class="flex shrink-0 items-center gap-1 sm:gap-2">
          <button
            type="button"
            :class="HEADER_BTN"
            :title="__('Send portal email')"
            @click="shareOpen = true"
          >
            <span :class="HEADER_TILE" aria-hidden="true">
              <LucideMail class="size-[15px]" />
            </span>
            <span class="sr-only lg:not-sr-only">{{
              __("Send portal email")
            }}</span>
          </button>
          <router-link
            v-if="auth.isAdmin || auth.isManager || auth.isProjectManager"
            :to="{ name: 'ContentPlans' }"
            :class="HEADER_BTN"
            :title="__('Monthly plans')"
          >
            <span :class="HEADER_TILE" aria-hidden="true">
              <LucideCalendarSync class="size-[15px]" />
            </span>
            <span class="sr-only lg:not-sr-only">{{
              __("Monthly plans")
            }}</span>
          </router-link>
          <router-link
            :to="{ name: 'ContentReport' }"
            :class="HEADER_BTN"
            :title="__('Delivery report')"
          >
            <span :class="HEADER_TILE" aria-hidden="true">
              <LucideChartColumn class="size-[15px]" />
            </span>
            <span class="sr-only lg:not-sr-only">{{
              __("Delivery report")
            }}</span>
          </router-link>
          <button
            v-if="auth.canEditContent"
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-[10px] bg-brand px-3 text-sm font-semibold text-brand-on shadow-sm transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 sm:px-4"
            @click="openAdd()"
          >
            <LucidePlus class="size-4" aria-hidden="true" />
            <span class="sr-only sm:not-sr-only">{{ __("Add entry") }}</span>
          </button>
        </div>
      </header>
    </LayoutHeader>

    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2 md:px-6"
    >
      <Link
        v-model="filters.customer"
        doctype="HD Customer"
        class="w-full sm:w-auto"
        :placeholder="__('All customers')"
      >
        <template #target="{ togglePopover }">
          <button
            type="button"
            :class="[CONTROL, 'w-full sm:w-auto']"
            aria-haspopup="listbox"
            :aria-label="
              __('Customer: {0}', filters.customer || __('All customers'))
            "
            @click="togglePopover()"
          >
            <span :class="CONTROL_TILE" aria-hidden="true">
              <LucideBuilding2 class="size-3.5" />
            </span>
            <span
              class="min-w-0 flex-1 truncate text-left"
              :class="filters.customer ? 'text-ink-gray-9' : 'text-ink-gray-6'"
              >{{ filters.customer || __("All customers") }}</span
            >
            <LucideChevronDown
              class="size-3.5 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
          </button>
        </template>
      </Link>
      <Select
        v-model="filters.channel"
        :class="[CONTROL_SELECT, 'flex-1 sm:flex-none']"
        :options="[{ label: __('All channels'), value: '' }, ...platforms]"
        :aria-label="__('Channel')"
      >
        <template #trigger="{ displayValue }">
          <span :class="CONTROL_TILE" aria-hidden="true">
            <LucideShare2 class="size-3.5" />
          </span>
          <span
            class="min-w-0 flex-1 truncate text-left"
            :class="filters.channel ? 'text-ink-gray-9' : 'text-ink-gray-6'"
            >{{ displayValue || __("All channels") }}</span
          >
          <LucideChevronDown
            class="size-3.5 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
        </template>
      </Select>
      <Select
        v-model="filters.status"
        :class="[CONTROL_SELECT, 'flex-1 sm:flex-none']"
        :options="[{ label: __('All statuses'), value: '' }, ...STATUSES]"
        :aria-label="__('Status')"
      >
        <template #trigger="{ displayValue }">
          <span :class="CONTROL_TILE" aria-hidden="true">
            <LucideCircleDot class="size-3.5" />
          </span>
          <span
            class="min-w-0 flex-1 truncate text-left"
            :class="filters.status ? 'text-ink-gray-9' : 'text-ink-gray-6'"
            >{{ displayValue || __("All statuses") }}</span
          >
          <LucideChevronDown
            class="size-3.5 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
        </template>
      </Select>
      <Link
        v-model="filters.person"
        doctype="User"
        class="w-full sm:w-auto"
        :filters="{ enabled: 1, user_type: 'System User' }"
        :placeholder="__('Everyone')"
      >
        <template #target="{ togglePopover }">
          <button
            type="button"
            :class="[CONTROL, 'w-full sm:w-auto']"
            aria-haspopup="listbox"
            :aria-label="__('Person: {0}', personLabel || __('Everyone'))"
            @click="togglePopover()"
          >
            <span :class="CONTROL_TILE" aria-hidden="true">
              <LucideUsers class="size-3.5" />
            </span>
            <span
              class="min-w-0 flex-1 truncate text-left"
              :class="filters.person ? 'text-ink-gray-9' : 'text-ink-gray-6'"
              >{{ personLabel || __("Everyone") }}</span
            >
            <LucideChevronDown
              class="size-3.5 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
          </button>
        </template>
      </Link>
      <button
        v-if="hasFilters"
        type="button"
        class="inline-flex h-8 items-center rounded-[10px] px-2.5 text-sm font-medium text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
        @click="clearFilters"
      >
        {{ __("Clear") }}
      </button>
      <div class="hidden flex-1 sm:block" />
      <div
        v-if="view === 'calendar'"
        class="hidden items-center gap-3 text-xs text-ink-gray-6 lg:flex"
        aria-hidden="true"
      >
        <span
          v-for="s in legend"
          :key="s.label"
          class="flex items-center gap-1.5"
        >
          <span class="size-2 rounded-sm" :class="s.swatch" />{{ s.label }}
        </span>
      </div>
      <button
        type="button"
        class="inline-flex h-8 items-center gap-1.5 rounded-[10px] border pl-1 pr-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
        :class="
          myPostsOn
            ? 'border-brand bg-brand-soft text-brand-ink'
            : 'border-dashed border-outline-gray-3 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-1'
        "
        :aria-pressed="myPostsOn"
        :title="__('Posts I am on, in any role')"
        @click="filters.person = myPostsOn ? '' : auth.userId"
      >
        <span
          class="grid size-[22px] place-items-center rounded-[6px]"
          :class="
            myPostsOn ? 'bg-brand text-brand-on' : 'bg-brand-soft text-brand'
          "
          aria-hidden="true"
        >
          <LucideUser class="size-3.5" />
        </span>
        {{ __("My posts") }}
      </button>
    </div>

    <div class="flex min-h-0 flex-1">
      <div
        class="relative flex min-w-0 flex-1 flex-col gap-3 px-4 pb-4 pt-3 md:px-6"
      >
        <div class="flex flex-wrap items-center gap-2">
          <div
            class="inline-flex h-8 items-center rounded-[10px] bg-surface-gray-2 p-0.5"
            role="group"
            :aria-label="__('View')"
          >
            <button
              v-for="v in VIEWS"
              :key="v.key"
              type="button"
              :aria-pressed="view === v.key"
              :class="[SEGMENT, view === v.key ? SEGMENT_ON : SEGMENT_OFF]"
              @click="view = v.key"
            >
              <component :is="v.icon" class="size-4" aria-hidden="true" />
              <span class="sr-only sm:not-sr-only">{{ v.label }}</span>
            </button>
          </div>
          <template v-if="view !== 'calendar'">
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="inline-flex h-8 items-center rounded-[10px] bg-surface-gray-2 px-3 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                :class="
                  includesToday
                    ? 'cursor-default text-ink-gray-5'
                    : 'text-ink-gray-8 hover:bg-surface-gray-3'
                "
                :disabled="includesToday"
                :title="__('Go to today (T)')"
                @click="anchor = today"
              >
                {{ __("Today") }}
              </button>
              <div
                class="inline-flex h-8 items-center divide-x divide-outline-gray-2 overflow-hidden rounded-[10px] border border-outline-gray-2 bg-surface-base"
              >
                <button
                  type="button"
                  :class="STEP_BTN"
                  :aria-label="__('Previous {0}', periodNoun)"
                  :title="__('Previous {0} (←)', periodNoun)"
                  @click="shiftPeriod(-1)"
                >
                  <LucideChevronLeft class="size-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  :class="STEP_BTN"
                  :aria-label="__('Next {0}', periodNoun)"
                  :title="__('Next {0} (→)', periodNoun)"
                  @click="shiftPeriod(1)"
                >
                  <LucideChevronRight class="size-4" aria-hidden="true" />
                </button>
              </div>
              <!-- the button opens the browser's date picker, anchored to the hidden input -->
              <span class="relative inline-flex">
                <button
                  type="button"
                  class="inline-flex h-8 items-center gap-1 rounded-[10px] px-2 text-lg font-semibold text-ink-gray-9 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                  :title="__('Pick a date')"
                  :aria-label="__('Pick a date, showing {0}', periodLabel)"
                  @click="openDatePicker"
                >
                  {{ periodLabel }}
                  <LucideChevronDown
                    class="size-4 text-ink-gray-5"
                    aria-hidden="true"
                  />
                </button>
                <input
                  ref="dateInput"
                  v-model="anchor"
                  type="date"
                  class="pointer-events-none absolute inset-0 opacity-0"
                  aria-hidden="true"
                  tabindex="-1"
                />
              </span>
            </div>
            <div class="flex-1" />
            <div
              class="inline-flex h-8 items-center rounded-[10px] bg-surface-gray-2 p-0.5"
              role="group"
              :aria-label="__('Period')"
            >
              <button
                v-for="p in PERIODS"
                :key="p.key"
                type="button"
                :aria-pressed="period === p.key"
                :class="[SEGMENT, period === p.key ? SEGMENT_ON : SEGMENT_OFF]"
                @click="period = p.key"
              >
                {{ p.label }}
              </button>
            </div>
          </template>
        </div>
        <div
          v-if="view !== 'calendar' && occasionsInRange.length"
          class="flex flex-wrap items-center gap-2"
          role="group"
          :aria-label="__('Occasions')"
        >
          <span class="mr-0.5 text-sm font-medium text-ink-gray-6">{{
            __("Occasions")
          }}</span>
          <button
            v-for="o in occasionsInRange"
            :key="`${o.date}-${o.occasion}`"
            type="button"
            class="inline-flex h-8 items-center gap-2 rounded-full border border-outline-gray-2 bg-surface-base pl-1 pr-3 text-sm text-ink-gray-8 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 disabled:cursor-default disabled:hover:bg-surface-base"
            :title="o.idea || ''"
            :aria-label="
              __(
                'Add an entry for {0} on {1}',
                o.occasion,
                dayjs(o.date).format('D MMMM')
              )
            "
            :disabled="!auth.canEditContent"
            @click="openAdd(o.date, o.occasion)"
          >
            <span
              class="grid size-6 place-items-center rounded-full bg-warning-soft text-warning"
              aria-hidden="true"
            >
              <LucideSparkles class="size-3" />
            </span>
            <span class="font-mono tabular-nums text-ink-gray-6">{{
              dayjs(o.date).format("D MMM")
            }}</span>
            {{ o.occasion }}
          </button>
        </div>
        <div
          v-if="view !== 'calendar' && period !== 'month'"
          class="grid grid-cols-7 gap-1 sm:gap-2"
          role="group"
          :aria-label="__('Days of the week')"
        >
          <button
            v-for="d in weekDays"
            :key="d.date"
            type="button"
            class="flex min-h-[54px] min-w-0 flex-col items-center justify-center gap-0.5 rounded-xl px-0.5 py-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 sm:h-[54px]"
            :class="
              d.selected
                ? 'border-2 border-brand bg-brand-soft'
                : 'border border-outline-gray-2 bg-surface-base hover:bg-surface-gray-1'
            "
            :aria-pressed="d.selected"
            :aria-label="d.ariaLabel"
            :title="d.special ? __('Special day: {0}', d.special) : undefined"
            @click="openDay(d.date)"
          >
            <span
              class="text-2xs font-semibold uppercase leading-none tracking-[0.08em]"
              :class="d.selected ? 'text-brand-ink' : 'text-ink-gray-6'"
              >{{ d.weekday }}</span
            >
            <span
              class="grid h-5 min-w-[1.5rem] place-items-center rounded-[6px] px-1 font-mono text-base font-medium leading-none tabular-nums"
              :class="
                d.selected
                  ? 'bg-brand text-brand-on'
                  : d.isToday
                  ? 'font-semibold text-brand-ink'
                  : 'text-ink-gray-9'
              "
              >{{ d.day }}</span
            >
            <span
              class="flex min-h-4 flex-wrap items-center justify-center gap-1 text-2xs tabular-nums"
            >
              <span
                v-if="d.count && d.missed"
                class="inline-flex h-4 items-center gap-1 rounded-full bg-danger-soft px-1.5 font-mono font-medium text-danger"
              >
                <span
                  class="size-[5px] rounded-full bg-danger"
                  aria-hidden="true"
                />{{ d.count }}
              </span>
              <span
                v-else-if="d.count"
                class="inline-flex h-4 items-center rounded-full bg-surface-gray-2 px-1.5 font-mono font-medium text-ink-gray-7"
                >{{ d.count }}</span
              >
              <span v-else class="text-ink-gray-4">–</span>
              <span
                v-if="d.special"
                class="grid size-4 place-items-center rounded-full bg-warning-soft text-warning"
              >
                <LucideStar class="size-2 fill-current" aria-hidden="true" />
              </span>
            </span>
          </button>
        </div>
        <!-- posts saved before a date was required have no slot, so list them here -->
        <div
          v-if="undated.data?.length"
          class="flex flex-col gap-2 rounded-xl border border-outline-gray-2 bg-surface-gray-1 px-3 py-1.5"
          role="status"
        >
          <div class="flex flex-wrap items-center gap-3">
            <span
              class="grid size-6 shrink-0 place-items-center rounded-[6px] border border-outline-gray-2 bg-surface-base text-ink-gray-6"
              aria-hidden="true"
            >
              <LucideCalendarX class="size-3.5" />
            </span>
            <p class="min-w-0 flex-1 text-sm text-ink-gray-8">
              {{ undatedText[0]
              }}<strong class="font-semibold text-ink-gray-9">{{
                undatedCount
              }}</strong
              >{{ undatedText[1] }}
            </p>
            <button
              type="button"
              class="inline-flex h-7 items-center rounded-[8px] border border-outline-gray-2 bg-surface-base px-2.5 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
              :aria-expanded="showUndated"
              @click="showUndated = !showUndated"
            >
              {{
                showUndated
                  ? __("Hide")
                  : undated.data.length === 1
                  ? __("Show it")
                  : __("Show them")
              }}
            </button>
          </div>
          <ul v-if="showUndated" class="flex flex-wrap gap-1.5">
            <li v-for="p in undated.data" :key="p.name">
              <button
                type="button"
                class="rounded-lg border border-outline-gray-2 bg-surface-base px-2.5 py-1 text-left text-sm text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                :title="__('Open it and set a posting date')"
                @click="openPost(p.name)"
              >
                {{ p.title }}
                <span class="text-xs text-ink-gray-5">· {{ p.customer }}</span>
              </button>
            </li>
          </ul>
        </div>
        <div
          v-if="(view === 'calendar' ? posts : monthPosts).error"
          class="absolute inset-x-4 top-4 z-10 flex items-center justify-between gap-3 rounded-xl bg-danger-soft px-4 py-2.5 text-base text-danger md:inset-x-8"
          role="alert"
        >
          {{ __("Couldn't load posts.") }}
          <Button size="sm" :label="__('Retry')" @click="refresh()" />
        </div>
        <!-- relative, so absolutely placed bits inside (screen-reader-only labels) are clipped
             by this list's scroll instead of stretching the whole page -->
        <div
          v-if="view !== 'calendar'"
          class="relative min-h-0 flex-1 overflow-y-auto"
        >
          <ContentBoard
            v-if="view === 'board'"
            :posts="visiblePosts"
            :month="rangeKey"
            :period="period"
            :day="period === 'day' ? anchor : ''"
            :loading="monthPosts.loading"
            :filters-customer="filters.customer"
            @open="openPost"
            @add="openAdd"
            @action="openAction"
          />
          <ContentSheet
            v-else
            :period="period"
            :posts="visiblePosts"
            :loading="monthPosts.loading"
            :filters-customer="filters.customer"
            @open="openPost"
          />
        </div>
        <Calendar
          v-else
          :events="events"
          :config="calendarConfig"
          :on-click="({ calendarEvent }) => openPost(String(calendarEvent.id))"
          :on-cell-click="onCellClick"
          @update="onReschedule"
          @range-change="onRangeChange"
        />
      </div>
    </div>

    <PostDialog
      v-model:open="dialogOpen"
      :post="selectedPost"
      @saved="refresh"
    />
    <AddEntryDialog
      v-model:open="addOpen"
      :customer="filters.customer"
      :date="addDate"
      :special-day="addSpecialDay"
      @saved="refresh"
    />
    <EntryActionDialog
      v-model:open="actionOpen"
      :post="actionPost"
      :action="actionKind"
      :role="actionRole"
      @done="refresh"
    />
    <SharePortalDialog v-model:open="shareOpen" :customer="filters.customer" />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import {
  Button,
  Calendar,
  call,
  createResource,
  dayjs,
  Select,
  toast,
} from "frappe-ui";
import { useEventListener, useStorage } from "@vueuse/core";
import { computed, markRaw, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideLayoutList from "~icons/lucide/layout-list";
import LucidePlus from "~icons/lucide/plus";
import LucideMail from "~icons/lucide/mail";
import LucideShare2 from "~icons/lucide/share-2";
import LucideSheet from "~icons/lucide/sheet";
import LucideCalendarSync from "~icons/lucide/calendar-sync";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideStar from "~icons/lucide/star";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideUser from "~icons/lucide/user";
import LucideUsers from "~icons/lucide/users";
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import {
  type ContentOccasion,
  type ContentPost,
  type EntryAction,
  isMissed,
  platformsOf,
  stageColor,
  STATUSES,
  TEAM_ROLES,
  type TeamRole,
} from "./constants";
import { useContentOptions } from "./contentOptions";
import AddEntryDialog from "./components/AddEntryDialog.vue";
import ContentBoard from "./components/ContentBoard.vue";
import ContentSheet from "./components/ContentSheet.vue";
import EntryActionDialog from "./components/EntryActionDialog.vue";
import PostDialog from "./components/PostDialog.vue";
import SharePortalDialog from "./components/SharePortalDialog.vue";

// dragging a post reschedules it, which only editors may do
const calendarConfig = computed(() => ({
  defaultMode: "Month",
  disableModes: ["Day"],
  isEditMode: useAuthStore().canEditContent,
  enableShortcuts: false,
  timeFormat: "12h",
  eventIcons: {},
}));

// shared looks for the header, filter bar and toolbar controls
const HEADER_BTN =
  "inline-flex h-8 items-center gap-1.5 rounded-[10px] px-1 text-sm font-medium text-ink-gray-8 transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 lg:pr-3";
const HEADER_TILE =
  "grid size-6 place-items-center rounded-[7px] bg-surface-gray-2 text-ink-gray-7";
const CONTROL =
  "inline-flex h-8 min-w-[130px] items-center gap-1.5 rounded-[10px] border border-outline-gray-2 bg-surface-base pl-1 pr-2 text-sm transition-colors hover:border-outline-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3";
// the Select trigger brings its own size and padding, so these win over it
const CONTROL_SELECT =
  "!h-8 !min-h-8 min-w-[130px] !gap-1.5 !rounded-[10px] !border-outline-gray-2 !bg-surface-base !pl-1 !pr-2 !text-sm hover:!border-outline-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3";
const CONTROL_TILE =
  "grid size-5 shrink-0 place-items-center rounded-[5px] border border-outline-gray-2 text-ink-gray-6";
const SEGMENT =
  "inline-flex h-7 items-center gap-1.5 rounded-[8px] px-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3";
// the same brand fill as frappe-ui's TabButtons (theme.css)
const SEGMENT_ON = "bg-brand font-semibold text-brand-on";
const SEGMENT_OFF = "font-medium text-ink-gray-6 hover:text-ink-gray-8";
const STEP_BTN =
  "grid h-full w-8 place-items-center text-ink-gray-7 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-3";

const legend = [
  { label: __("Planning"), swatch: "bg-info" },
  { label: __("In review"), swatch: "bg-warning" },
  { label: __("Approved"), swatch: "bg-brand" },
  { label: __("Published"), swatch: "bg-success" },
];

type View = "board" | "calendar" | "sheet";
const VIEWS: { key: View; label: string; icon: unknown }[] = [
  { key: "board", label: __("Board"), icon: markRaw(LucideLayoutList) },
  { key: "calendar", label: __("Calendar"), icon: markRaw(LucideCalendarDays) },
  { key: "sheet", label: __("Sheet"), icon: markRaw(LucideSheet) },
];
const view = useStorage<View>("helpdesk-content-view", "board");

type Period = "day" | "week" | "month";
const PERIODS: { key: Period; label: string }[] = [
  { key: "day", label: __("Day") },
  { key: "week", label: __("Week") },
  { key: "month", label: __("Month") },
];
const period = useStorage<Period>("helpdesk-content-period", "month");
const today = dayjs().format("YYYY-MM-DD");
// any date inside the period on screen; the period is worked out from it
const anchor = ref(today);

const rangeStart = computed(() =>
  dayjs(anchor.value || today).startOf(period.value)
);
const rangeEnd = computed(() =>
  dayjs(anchor.value || today).endOf(period.value)
);
// Day view loads its whole week so the day strip can show counts
const fetchStart = computed(() =>
  period.value === "day" ? rangeStart.value.startOf("week") : rangeStart.value
);
const fetchEnd = computed(() =>
  period.value === "day" ? rangeEnd.value.endOf("week") : rangeEnd.value
);
const rangeKey = computed(
  () => `${period.value}:${rangeStart.value.format("YYYY-MM-DD")}`
);
const fetchKey = computed(
  () =>
    `${fetchStart.value.format("YYYY-MM-DD")}:${fetchEnd.value.format(
      "YYYY-MM-DD"
    )}`
);

const visiblePosts = computed(() =>
  (monthPosts.data ?? []).filter((p: ContentPost) => {
    const d = dayjs(p.publish_on);
    return !d.isBefore(rangeStart.value) && !d.isAfter(rangeEnd.value);
  })
);

const weekDays = computed(() => {
  const start = dayjs(anchor.value || today).startOf("week");
  const posts: ContentPost[] = monthPosts.data ?? [];
  return Array.from({ length: 7 }, (_, i) => {
    const day = start.add(i, "day");
    const date = day.format("YYYY-MM-DD");
    const onDay = posts.filter(
      (p) => dayjs(p.publish_on).format("YYYY-MM-DD") === date
    );
    const missed = onDay.some((p) => isMissed(p));
    const special = onDay.find((p) => p.special_day)?.special_day;
    const isToday = date === today;
    return {
      date,
      weekday: day.format("ddd"),
      day: day.format("D"),
      count: onDay.length,
      missed,
      special,
      isToday,
      selected: period.value === "day" && date === anchor.value,
      ariaLabel: `${day.format("dddd D MMMM")}${
        isToday ? `, ${__("today")}` : ""
      }: ${onDay.length} ${onDay.length === 1 ? __("post") : __("posts")}${
        missed ? `, ${__("some missed")}` : ""
      }${special ? `, ${__("special day: {0}", special)}` : ""}`,
    };
  });
});

function openDay(date: string) {
  anchor.value = date;
  period.value = "day";
}

const dateInput = ref<HTMLInputElement | null>(null);
function openDatePicker() {
  const input = dateInput.value;
  if (!input) return;
  try {
    input.showPicker();
  } catch {
    input.focus();
  }
}

// ← / → move by a period, T jumps to today (not while typing)
useEventListener(window, "keydown", (e: KeyboardEvent) => {
  if (view.value === "calendar" || e.metaKey || e.ctrlKey || e.altKey) return;
  const target = e.target as HTMLElement | null;
  if (
    target?.closest(
      "input, textarea, select, [contenteditable], [role=dialog], [role=combobox], [role=listbox]"
    )
  )
    return;
  if (e.key === "ArrowLeft") shiftPeriod(-1);
  else if (e.key === "ArrowRight") shiftPeriod(1);
  else if (e.key === "t" || e.key === "T") anchor.value = today;
  else return;
  e.preventDefault();
});
const includesToday = computed(
  () =>
    !dayjs(today).isBefore(rangeStart.value, "day") &&
    !dayjs(today).isAfter(rangeEnd.value, "day")
);
const periodNoun = computed(
  () => ({ day: __("day"), week: __("week"), month: __("month") }[period.value])
);
const periodLabel = computed(() => {
  const start = rangeStart.value;
  if (period.value === "day") return start.format("ddd, D MMM YYYY");
  if (period.value === "month") return start.format("MMMM YYYY");
  const end = rangeEnd.value;
  return start.month() === end.month()
    ? `${start.format("D")} – ${end.format("D MMM YYYY")}`
    : `${start.format("D MMM")} – ${end.format("D MMM YYYY")}`;
});

function shiftPeriod(by: number) {
  anchor.value = dayjs(anchor.value || today)
    .add(by, period.value)
    .format("YYYY-MM-DD");
}

const filters = reactive({ customer: "", channel: "", status: "", person: "" });
const range = ref<{ start: string; end: string } | null>(null);
const myPostsOn = computed(() => filters.person === auth.userId);
const userStore = useUserStore();
const personLabel = computed(() => {
  if (!filters.person) return "";
  const users: { name: string; full_name?: string }[] =
    userStore.users.data ?? [];
  return (
    users.find((u) => u.name === filters.person)?.full_name || filters.person
  );
});
const hasFilters = computed(
  () =>
    !!(filters.customer || filters.channel || filters.status || filters.person)
);

/** Posts the chosen person is on, in any role, each listed once. */
function personQuery() {
  const u = filters.person;
  if (!u) return {};
  return {
    or_filters: [
      ...TEAM_ROLES.map((r) => [r.field, "=", u]),
      // or one of several people on a role
      ["HD Content Post Member", "user", "=", u],
    ],
    // filtering on the member table joins it, which repeats a post once per member
    group_by: "`tabHD Content Post`.`name`",
  };
}

function baseFilters() {
  const f: Record<string, unknown> = {};
  if (filters.customer) f.customer = filters.customer;
  // a post can go out on several platforms; channel is only the first
  if (filters.channel) f.platforms = ["like", `%${filters.channel}%`];
  // cancelled posts stay off the calendar unless asked for
  f.status = filters.status || ["!=", "Cancelled"];
  return f;
}

const FIELDS = [
  "name",
  "title",
  "status",
  "channel",
  "platforms",
  "customer",
  "special_day",
  "publish_on",
];

const posts = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "HD Content Post",
    fields: FIELDS,
    filters: {
      ...baseFilters(),
      publish_on: ["between", [range.value!.start, range.value!.end]],
    },
    ...personQuery(),
    order_by: "publish_on asc",
    limit_page_length: 1000,
  }),
});

// Board and Sheet show cancelled posts too, behind their own filter
const BOARD_FIELDS = [
  ...FIELDS,
  "format",
  "caption",
  "brief",
  "writer",
  "designer",
  "marketer",
  "video_editor",
  "writer_hours",
  "designer_hours",
  "video_editor_hours",
  "marketer_hours",
  "published_on",
  "published_url",
  "times_postponed",
];
const monthPosts = createResource({
  url: "frappe.client.get_list",
  makeParams: () => {
    const f = baseFilters();
    if (!filters.status) delete f.status;
    return {
      doctype: "HD Content Post",
      fields: BOARD_FIELDS,
      filters: {
        ...f,
        publish_on: [
          "between",
          [
            fetchStart.value.format("YYYY-MM-DD 00:00:00"),
            fetchEnd.value.format("YYYY-MM-DD 23:59:59"),
          ],
        ],
      },
      ...personQuery(),
      order_by: "publish_on asc",
      limit_page_length: 1000,
    };
  },
});

const auth = useAuthStore();
const { platforms } = useContentOptions();

// festivals and national days in the period; a customer's package picks its regions
const occasions = createResource({
  url: "helpdesk.api.content_board.get_occasions",
  makeParams: () => ({
    start: fetchStart.value.format("YYYY-MM-DD"),
    end: fetchEnd.value.format("YYYY-MM-DD"),
    customer: filters.customer || undefined,
  }),
});
const occasionsInRange = computed<ContentOccasion[]>(() =>
  (occasions.data ?? []).filter(
    (o: ContentOccasion) =>
      !dayjs(o.date).isBefore(rangeStart.value, "day") &&
      !dayjs(o.date).isAfter(rangeEnd.value, "day")
  )
);

const events = computed(() =>
  (posts.data ?? []).map((p: ContentPost) => {
    const start = dayjs(p.publish_on);
    return {
      id: p.name,
      // ★ marks a special-day post on the month and week grid
      title: `${p.special_day ? `★ ${p.special_day} · ` : ""}${platformsOf(
        p
      ).join(", ")} · ${p.title}`,
      participant: `${p.status} · ${p.customer}`,
      fromDate: start.format("YYYY-MM-DD"),
      toDate: start.format("YYYY-MM-DD"),
      fromTime: start.format("HH:mm"),
      toTime: start.add(30, "minute").format("HH:mm"),
      color: stageColor(p.status),
    };
  })
);

function onRangeChange({
  startDate,
  endDate,
}: {
  startDate: string;
  endDate: string;
}) {
  range.value = {
    start: dayjs(startDate).startOf("day").format("YYYY-MM-DD HH:mm:ss"),
    end: dayjs(endDate).endOf("day").format("YYYY-MM-DD HH:mm:ss"),
  };
  posts.reload();
}

// posts saved before a posting date was required; opening one asks for a date
const showUndated = ref(false);
const undated = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "HD Content Post",
    fields: ["name", "title", "customer"],
    filters: {
      ...baseFilters(),
      // a cancelled post needs no date, so it never needs fixing
      status:
        filters.status && filters.status !== "Cancelled"
          ? filters.status
          : ["!=", "Cancelled"],
      publish_on: ["is", "not set"],
    },
    ...personQuery(),
    order_by: "creation desc",
    limit_page_length: 100,
  }),
});

// the count and its noun are set in bold, so split the translated sentence around them
const COUNT_MARK = "\u0000";
const undatedCount = computed(() => {
  const n = undated.data?.length ?? 0;
  return n === 1 ? __("1 post") : __("{0} posts", n);
});
const undatedText = computed(() => {
  const n = undated.data?.length ?? 0;
  const sentence =
    n === 1
      ? __("{0} has no posting date, so it isn't on the calendar.", COUNT_MARK)
      : __(
          "{0} have no posting date, so they aren't on the calendar.",
          COUNT_MARK
        );
  // a translation may drop or repeat the placeholder: show the count once, keep all its text
  const parts = sentence.split(COUNT_MARK);
  if (parts.length === 1) return ["", ` ${sentence}`];
  return [parts[0], parts.slice(1).join("")];
});

function refresh() {
  undated.reload();
  if (view.value === "calendar") {
    if (range.value) posts.reload();
  } else {
    monthPosts.reload();
    occasions.reload();
  }
}

watch(filters, refresh);
watch([view, fetchKey], refresh, { immediate: true });

function clearFilters() {
  Object.assign(filters, { customer: "", channel: "", status: "", person: "" });
}

// Dragging a post to another day or time reschedules it; roll back if the server refuses
async function onReschedule(event: {
  id?: string | number;
  fromDate?: string;
  fromTime?: string;
}) {
  const publishOn = dayjs(
    `${event.fromDate} ${event.fromTime || "10:00"}`
  ).format("YYYY-MM-DD HH:mm:ss");
  try {
    await call("frappe.client.set_value", {
      doctype: "HD Content Post",
      name: String(event.id),
      fieldname: "publish_on",
      value: publishOn,
    });
    toast.success(
      __("Rescheduled to {0}", dayjs(publishOn).format("D MMM, h:mm A"))
    );
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't reschedule this post"));
  } finally {
    posts.reload();
  }
}

// --- dialog ---

const dialogOpen = ref(false);
const shareOpen = ref(false);
const selectedPost = ref<{ name?: string; publish_on?: string } | null>(null);

function openPost(name: string) {
  selectedPost.value = { name };
  dialogOpen.value = true;
}

// Missed-post alert emails link to /content?post=<name>
const route = useRoute();
if (typeof route.query.post === "string") openPost(route.query.post);

const addOpen = ref(false);
const addDate = ref("");
const addSpecialDay = ref("");

// an occasion chip fills in its name as the entry's special day
function openAdd(date?: string, specialDay?: string) {
  if (!auth.canEditContent) return;
  addDate.value = date || "";
  addSpecialDay.value = specialDay || "";
  addOpen.value = true;
}

function onCellClick({ date }: { date: Date | string }) {
  openAdd(dayjs(date).format("YYYY-MM-DD"));
}

const actionOpen = ref(false);
const actionPost = ref<ContentPost | null>(null);
const actionKind = ref<EntryAction | null>(null);
const actionRole = ref<TeamRole | undefined>();

function openAction(post: ContentPost, action: EntryAction, role?: TeamRole) {
  actionPost.value = post;
  actionKind.value = action;
  actionRole.value = role;
  actionOpen.value = true;
}
</script>
