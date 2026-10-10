<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Calendar") }}</div>
      </template>
      <template #right-header>
        <TabButtons
          v-if="data?.can_see_team"
          v-model="scope"
          :buttons="[
            { label: __('Mine'), value: 'mine' },
            { label: __('Team'), value: 'team' },
          ]"
        />
        <Button
          variant="ghost"
          :loading="loading"
          :aria-label="__('Refresh')"
          @click="load"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div
      class="flex min-h-0 flex-1 flex-col gap-3 px-4 py-4 md:px-6"
      :aria-busy="loading"
    >
      <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <ul
          role="list"
          class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-6"
          :aria-label="__('Legend')"
        >
          <li
            v-for="item in LEGEND"
            :key="item.kind"
            class="flex items-center gap-1.5"
          >
            <component
              :is="KINDS[item.kind].icon"
              class="size-3.5"
              :class="iconTone(item.kind)"
              aria-hidden="true"
            />
            {{ item.label }}
          </li>
        </ul>
        <p
          v-if="
            !isMobileView && data && !loading && !loadError && !events.length
          "
          class="text-p-xs text-ink-gray-5"
        >
          {{ emptyText }}
        </p>
      </div>

      <div
        v-if="loadError"
        role="alert"
        class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-outline-gray-2 bg-danger-soft px-3 py-2"
      >
        <p class="flex items-center gap-2 text-p-sm text-danger">
          <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
          {{ errorText(loadError, __("Couldn't load the calendar.")) }}
        </p>
        <Button size="sm" :label="__('Retry')" @click="load" />
      </div>

      <!-- phones: an agenda for the week instead of a squeezed grid -->
      <section
        v-if="isMobileView"
        class="flex min-h-0 flex-1 flex-col"
        :aria-label="__('Agenda')"
      >
        <div class="flex items-center justify-between gap-2 pb-2">
          <h2 class="text-base-medium tabular-nums text-ink-gray-9">
            {{ weekLabel }}
          </h2>
          <div class="flex items-center gap-1">
            <Button
              variant="ghost"
              :aria-label="__('Previous week')"
              @click="shiftWeek(-1)"
            >
              <template #icon>
                <LucideChevronLeft class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button variant="ghost" :label="__('Today')" @click="setWeek()" />
            <Button
              variant="ghost"
              :aria-label="__('Next week')"
              @click="shiftWeek(1)"
            >
              <template #icon>
                <LucideChevronRight class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </div>

        <div v-if="loading && !calendarData">
          <p role="status" class="sr-only">{{ __("Loading calendar") }}</p>
          <div class="flex flex-col gap-2" aria-hidden="true">
            <div
              v-for="i in 4"
              :key="i"
              class="h-14 animate-pulse rounded-lg bg-surface-gray-2"
            />
          </div>
        </div>

        <TaskyState
          v-else-if="!agenda.length && !loadError"
          :icon="LucideCalendarCheck"
          :title="__('Nothing this week')"
          :message="emptyText"
        />

        <div v-else class="min-h-0 flex-1 overflow-y-auto">
          <section
            v-for="day in agenda"
            :key="day.date"
            class="mb-4"
            :aria-labelledby="`agenda-${day.date}`"
          >
            <h3
              :id="`agenda-${day.date}`"
              class="mb-1.5 flex items-center gap-2 text-sm text-ink-gray-6"
            >
              <span
                :class="day.isToday ? 'text-base-medium text-brand-ink' : ''"
              >
                {{ day.label }}
              </span>
              <span
                v-if="day.isToday"
                class="rounded bg-brand-soft px-1.5 text-xs text-brand-ink"
              >
                {{ __("Today") }}
              </span>
            </h3>
            <ul
              role="list"
              class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
            >
              <li
                v-for="event in day.events"
                :key="event.id"
                class="flex items-center gap-3 border-b border-outline-gray-1 px-3 py-2.5 last:border-b-0"
              >
                <component
                  :is="KINDS[event.type].icon"
                  class="size-4 shrink-0"
                  :class="iconTone(event.type)"
                  aria-hidden="true"
                />
                <component
                  :is="detail(event).route ? RouterLink : 'div'"
                  :to="detail(event).route ?? undefined"
                  class="flex min-w-0 flex-1 flex-col rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                >
                  <span class="truncate text-base text-ink-gray-9">
                    {{ event.title }}
                  </span>
                  <span class="truncate text-p-xs text-ink-gray-6">
                    <span class="font-mono tabular-nums">
                      {{ timeLabel(event) }}
                    </span>
                    <template v-if="detail(event).context">
                      · {{ detail(event).context }}
                    </template>
                  </span>
                </component>
                <Button
                  v-if="detail(event).joinUrl"
                  size="sm"
                  :label="__('Join')"
                  :icon-left="LucideVideo"
                  :link="detail(event).joinUrl"
                />
              </li>
            </ul>
          </section>
        </div>
      </section>

      <div v-else class="work-calendar min-h-0 flex-1">
        <Calendar
          :events="events"
          :config="calendarConfig"
          @range-change="onRangeChange"
        >
          <template
            #header="{
              currentMonthYear,
              enabledModes,
              activeView,
              decrement,
              increment,
              updateActiveView,
              setCalendarDate,
              onMonthYearChange,
              selectedMonthDate,
            }"
          >
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
              <!-- the month is also the date picker: jump to any month or day -->
              <h2>
                <DatePicker
                  :model-value="selectedMonthDate"
                  :clearable="false"
                  @update:model-value="onMonthYearChange"
                >
                  <template #target="{ togglePopover }">
                    <Button
                      variant="ghost"
                      class="text-lg-medium tabular-nums text-ink-gray-9"
                      :label="currentMonthYear"
                      :aria-label="
                        __('{0}, pick a date', [String(currentMonthYear)])
                      "
                      @click="togglePopover"
                    >
                      <template #suffix>
                        <LucideChevronDown
                          class="size-4 text-ink-gray-5"
                          aria-hidden="true"
                        />
                      </template>
                    </Button>
                  </template>
                </DatePicker>
              </h2>
              <div class="flex items-center gap-1">
                <Button
                  variant="ghost"
                  :aria-label="__('Previous')"
                  @click="decrement"
                >
                  <template #icon>
                    <LucideChevronLeft class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <Button
                  variant="ghost"
                  :label="__('Today')"
                  @click="setCalendarDate()"
                />
                <Button
                  variant="ghost"
                  :aria-label="__('Next')"
                  @click="increment"
                >
                  <template #icon>
                    <LucideChevronRight class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <TabButtons
                  class="ml-2"
                  :buttons="
                    enabledModes.map((mode) => ({
                      label: __(mode.label),
                      value: mode.value,
                    }))
                  "
                  :model-value="activeView"
                  @update:model-value="updateActiveView"
                />
              </div>
            </div>
          </template>
          <template #event-popover-content="{ calendarEvent, close }">
            <div class="flex w-72 flex-col gap-2 p-3 text-sm">
              <p class="text-base-medium text-ink-gray-9">
                {{ detail(calendarEvent).title }}
              </p>
              <p class="font-mono text-xs tabular-nums text-ink-gray-6">
                {{ detail(calendarEvent).when }}
              </p>
              <p
                v-if="detail(calendarEvent).context"
                class="text-p-xs text-ink-gray-6"
              >
                {{ detail(calendarEvent).context }}
              </p>
              <div class="mt-1 flex flex-wrap gap-2">
                <Button
                  v-if="detail(calendarEvent).joinUrl"
                  size="sm"
                  variant="solid"
                  :label="__('Join')"
                  :icon-left="LucideVideo"
                  :link="detail(calendarEvent).joinUrl"
                />
                <Button
                  v-if="detail(calendarEvent).route"
                  size="sm"
                  :label="detail(calendarEvent).openLabel"
                  @click="open(detail(calendarEvent).route, close)"
                />
              </div>
            </div>
          </template>
        </Calendar>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useScreenSize } from "@/composables/screen";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import {
  Button,
  Calendar,
  CalendarColorMap,
  DatePicker,
  TabButtons,
  call,
  dayjs,
} from "frappe-ui";
import { computed, ref, watch, type Component } from "vue";
import { RouterLink, useRouter, type RouteLocationRaw } from "vue-router";
import LucideCalendarCheck from "~icons/lucide/calendar-check";
import LucideCalendarOff from "~icons/lucide/calendar-off";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideFlag from "~icons/lucide/flag";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTreePalm from "~icons/lucide/tree-palm";
import LucideVideo from "~icons/lucide/video";

interface MeetingEvent {
  name: string;
  subject: string;
  starts_on: string;
  ends_on: string;
  join_url: string | null;
  reference_doctype: "HD Ticket" | "Task";
  reference_name: string;
  customer: string | null;
}

interface TaskEvent {
  name: string;
  subject: string;
  project: string | null;
  project_name: string | null;
  status: string;
  exp_end_date: string;
  is_key: 0 | 1;
  is_milestone: 0 | 1;
}

/** a named holiday on the hub's holiday list (weekly offs are left out) */
interface HolidayEvent {
  date: string;
  description: string;
  /** from the holiday list on the CRM site */
  synced: boolean;
}

/** approved leave synced from the CRM site */
interface LeaveEvent {
  user: string;
  full_name: string;
  from_date: string;
  to_date: string;
  half_day: boolean;
}

interface CalendarData {
  meetings: MeetingEvent[];
  tasks: TaskEvent[];
  holidays: HolidayEvent[];
  leave: LeaveEvent[];
  can_see_team: boolean;
}

type Kind = "meeting" | "task" | "key" | "overdue" | "holiday" | "leave";

// frappe-ui's calendar only knows its own named colours (no neutral, no red)
// and looks them up in this exported map, so the TBO ones are added to it:
// neutral events, red only for overdue, brand for the selected event
const BRAND_ACTIVE = {
  borderActive: "var(--brand)",
  textActive: "var(--brand-ink)",
  subtextActive: "var(--brand-ink)",
  bgActive: "var(--brand-soft)",
};
Object.assign(CalendarColorMap, {
  "tbo-meeting": {
    ...BRAND_ACTIVE,
    color: "var(--ink-gray-7)",
    border: "var(--ink-gray-7)",
    text: "var(--ink-gray-8)",
    subtext: "var(--ink-gray-6)",
    bg: "var(--surface-gray-2)",
    bgHover: "var(--surface-gray-3)",
  },
  "tbo-task": {
    ...BRAND_ACTIVE,
    color: "var(--ink-gray-5)",
    border: "var(--outline-gray-4)",
    text: "var(--ink-gray-8)",
    subtext: "var(--ink-gray-6)",
    bg: "var(--surface-gray-1)",
    bgHover: "var(--surface-gray-2)",
  },
  "tbo-overdue": {
    ...BRAND_ACTIVE,
    color: "var(--danger)",
    border: "var(--danger)",
    text: "var(--danger)",
    subtext: "var(--ink-gray-6)",
    bg: "var(--danger-soft)",
    bgHover: "var(--danger-soft)",
  },
  // a day off coming up: the quiet info tone, never loud
  "tbo-holiday": {
    ...BRAND_ACTIVE,
    color: "var(--info)",
    border: "var(--info)",
    text: "var(--ink-gray-8)",
    subtext: "var(--ink-gray-6)",
    bg: "var(--info-soft)",
    bgHover: "var(--info-soft)",
  },
});

const KINDS: Record<Kind, { color: string; icon: Component }> = {
  meeting: { color: "tbo-meeting", icon: LucideVideo },
  task: { color: "tbo-task", icon: LucideCircleDot },
  key: { color: "tbo-task", icon: LucideFlag },
  overdue: { color: "tbo-overdue", icon: LucideCircleAlert },
  holiday: { color: "tbo-holiday", icon: LucideCalendarOff },
  leave: { color: "tbo-task", icon: LucideTreePalm },
};

const LEGEND: { kind: Kind; label: string }[] = [
  { kind: "meeting", label: __("Teams meeting") },
  { kind: "task", label: __("Task due") },
  { kind: "key", label: __("Key task or milestone") },
  { kind: "overdue", label: __("Overdue task") },
  { kind: "holiday", label: __("Holiday") },
  { kind: "leave", label: __("On leave") },
];

/** the icon's tone: red for overdue, info for holidays, else neutral */
function iconTone(kind: Kind) {
  return kind === "overdue"
    ? "text-danger"
    : kind === "holiday"
    ? "text-info"
    : "text-ink-gray-5";
}

const calendarConfig = {
  defaultMode: "Week",
  isEditMode: false,
  enableShortcuts: false,
  timeFormat: "24h",
  scrollToHour: 8,
  eventIcons: Object.fromEntries(
    Object.entries(KINDS).map(([kind, { icon }]) => [kind, icon])
  ),
};

const router = useRouter();
const { isMobileView } = useScreenSize();
const scope = ref<"mine" | "team">("mine");
// the week the calendar opens on, until it reports its own range
const range = ref(weekRange(dayjs()));

function weekRange(day: ReturnType<typeof dayjs>) {
  return {
    start: day.startOf("week").format("YYYY-MM-DD"),
    end: day.endOf("week").format("YYYY-MM-DD"),
  };
}

// only the latest request may fill the calendar: weeks clicked through quickly
// (or Mine/Team flipped) must not be overwritten by a slower, older answer
let latestRequest = 0;
const calendarData = ref<CalendarData | null>(null);
const loading = ref(false);
const loadError = ref<any>(null);

async function load() {
  const request = ++latestRequest;
  loading.value = true;
  try {
    const result = await call("helpdesk.api.calendar.get_calendar", {
      start: range.value.start,
      end: range.value.end,
      team: scope.value === "team" ? 1 : 0,
    });
    if (request === latestRequest) {
      calendarData.value = result;
      loadError.value = null;
    }
  } catch (e) {
    if (request === latestRequest) loadError.value = e;
  } finally {
    if (request === latestRequest) loading.value = false;
  }
}

// the desktop calendar reports its range as soon as it mounts, which loads it
if (isMobileView.value) load();
watch(scope, load);

const data = computed(() => calendarData.value);

// the month view also shows the last days of the previous month and the
// first of the next, but reports only the month itself
const MONTH_VIEW_DAYS = 28;
const PADDING_DAYS = 7;

function onRangeChange({
  startDate,
  endDate,
}: {
  startDate: string;
  endDate: string;
}) {
  let start = dayjs(startDate);
  let end = dayjs(endDate);
  if (end.diff(start, "day") >= MONTH_VIEW_DAYS) {
    start = start.subtract(PADDING_DAYS, "day");
    end = end.add(PADDING_DAYS, "day");
  }
  range.value = {
    start: start.format("YYYY-MM-DD"),
    end: end.format("YYYY-MM-DD"),
  };
  load();
}

// --- agenda (phones) ---

function setWeek(day = dayjs()) {
  range.value = weekRange(day);
  load();
}

function shiftWeek(weeks: number) {
  setWeek(dayjs(range.value.start).add(weeks, "week"));
}

// turning a tablet to portrait swaps the grid for the agenda on this week
watch(isMobileView, (mobile) => {
  if (mobile) setWeek();
});

const weekLabel = computed(() => {
  const start = dayjs(range.value.start);
  const end = dayjs(range.value.end);
  return start.month() === end.month()
    ? `${start.format("D")}–${end.format("D MMM YYYY")}`
    : `${start.format("D MMM")}–${end.format("D MMM YYYY")}`;
});

const agenda = computed(() => {
  const today = dayjs().format("YYYY-MM-DD");
  const byDay = new Map<string, typeof events.value>();
  // an event appears on every day of the week it spans (a meeting past midnight)
  for (const event of events.value) {
    const first =
      event.fromDate > range.value.start ? event.fromDate : range.value.start;
    const last =
      event.toDate < range.value.end ? event.toDate : range.value.end;
    for (
      let day = dayjs(first);
      !day.isAfter(last, "day");
      day = day.add(1, "day")
    ) {
      const date = day.format("YYYY-MM-DD");
      if (!byDay.has(date)) byDay.set(date, []);
      byDay.get(date)!.push(event);
    }
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, items]) => ({
      date,
      isToday: date === today,
      label: dayjs(date).format("dddd D MMM"),
      // meetings by start time, then the day's due tasks
      events: [...items].sort((a, b) =>
        (a.fromTime ?? "99").localeCompare(b.fromTime ?? "99")
      ),
    }));
});

function timeLabel(event: typeof events.value[number]) {
  if (event.fromTime) return `${event.fromTime}–${event.toTime}`;
  return (
    {
      overdue: __("Overdue"),
      holiday: __("Holiday"),
      leave: __("All day"),
    }[event.type as string] ?? __("Due")
  );
}

const emptyText = computed(() =>
  scope.value === "team"
    ? __("No team meetings or open tasks due in this range.")
    : __("No meetings or open tasks of yours due in this range.")
);

// --- events ---

const events = computed(() => {
  const today = dayjs().format("YYYY-MM-DD");
  const meetings = (data.value?.meetings ?? []).map((m) => {
    const start = dayjs(m.starts_on);
    const end = dayjs(m.ends_on);
    return {
      id: `meeting:${m.name}`,
      title: m.subject,
      participant: m.customer || "",
      fromDate: start.format("YYYY-MM-DD"),
      toDate: end.format("YYYY-MM-DD"),
      fromTime: start.format("HH:mm"),
      toTime: end.format("HH:mm"),
      type: "meeting" as Kind,
      color: KINDS.meeting.color,
      kind: "meeting",
      record: m,
    };
  });
  const tasks = (data.value?.tasks ?? []).map((t) => {
    const type: Kind =
      t.exp_end_date < today
        ? "overdue"
        : t.is_key || t.is_milestone
        ? "key"
        : "task";
    return {
      id: `task:${t.name}`,
      title: t.subject,
      participant: t.project_name || "",
      fromDate: t.exp_end_date,
      toDate: t.exp_end_date,
      fromTime: undefined as string | undefined,
      toTime: undefined as string | undefined,
      isFullDay: true,
      type,
      color: KINDS[type].color,
      kind: "task",
      record: t,
    };
  });
  const allDay = (
    id: string,
    title: string,
    date: string,
    type: Kind,
    record: unknown
  ) => ({
    id,
    title,
    participant: "",
    fromDate: date,
    toDate: date,
    fromTime: undefined as string | undefined,
    toTime: undefined as string | undefined,
    isFullDay: true,
    type,
    color: KINDS[type].color,
    kind: type,
    record,
  });
  const holidays = (data.value?.holidays ?? []).map((h) =>
    allDay(
      `holiday:${h.date}`,
      h.description || __("Holiday"),
      h.date,
      "holiday",
      h
    )
  );
  // one all-day event per day of the leave inside the range shown
  const leave = (data.value?.leave ?? []).flatMap((l) => {
    const days = [];
    const last = l.to_date < range.value.end ? l.to_date : range.value.end;
    for (
      let day = dayjs(
        l.from_date > range.value.start ? l.from_date : range.value.start
      );
      !day.isAfter(last, "day");
      day = day.add(1, "day")
    ) {
      const date = day.format("YYYY-MM-DD");
      days.push(
        allDay(
          `leave:${l.user}:${date}`,
          l.half_day
            ? __("{0} · Half day leave", l.full_name)
            : __("{0} · On leave", l.full_name),
          date,
          "leave",
          l
        )
      );
    }
    return days;
  });
  return [...holidays, ...leave, ...meetings, ...tasks];
});

function detail(event: Record<string, any>) {
  if (event.kind === "holiday") {
    const h = event.record as HolidayEvent;
    return {
      title: h.description || __("Holiday"),
      when: dayjs(h.date).format("dddd D MMM YYYY"),
      context: h.synced
        ? __("From the holiday list on the CRM site")
        : __("Business holiday"),
      joinUrl: null,
      route: null,
      openLabel: "",
    };
  }
  if (event.kind === "leave") {
    const l = event.record as LeaveEvent;
    const from = dayjs(l.from_date);
    const to = dayjs(l.to_date);
    return {
      title: event.title,
      when: from.isSame(to, "day")
        ? from.format("ddd D MMM")
        : `${from.format("ddd D MMM")}–${to.format("ddd D MMM")}`,
      context: __("Approved leave"),
      joinUrl: null,
      route: null,
      openLabel: "",
    };
  }
  if (event.kind === "meeting") {
    const m = event.record as MeetingEvent;
    const isTicket = m.reference_doctype === "HD Ticket";
    return {
      title: m.subject,
      when: `${dayjs(m.starts_on).format("ddd D MMM, HH:mm")}–${dayjs(
        m.ends_on
      ).format("HH:mm")}`,
      context: [
        isTicket
          ? __("Ticket #{0}", m.reference_name)
          : __("Task {0}", m.reference_name),
        m.customer,
      ]
        .filter(Boolean)
        .join(" · "),
      joinUrl: m.join_url,
      route: isTicket
        ? { name: "TicketAgent", params: { ticketId: m.reference_name } }
        : null,
      openLabel: __("Open ticket"),
    };
  }
  const t = event.record as TaskEvent;
  return {
    title: t.subject,
    when: __("Due {0}", dayjs(t.exp_end_date).format("ddd D MMM")),
    context: [t.name, t.project_name, t.status].filter(Boolean).join(" · "),
    joinUrl: null,
    route: t.project
      ? { name: "TaskyProject", params: { projectId: t.project } }
      : null,
    openLabel: __("Open project"),
  };
}

function open(route: RouteLocationRaw | null, close: () => void) {
  if (!route) return;
  close();
  router.push(route);
}
</script>

<style scoped>
/* today's date is the calendar's one highlighted day: brand, not black */
.work-calendar :deep(.bg-surface-gray-10.size-\[25px\]) {
  background-color: var(--brand);
  color: var(--on-brand);
}
</style>
