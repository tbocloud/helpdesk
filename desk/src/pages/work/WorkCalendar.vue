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

    <div class="flex min-h-0 flex-1 flex-col gap-3 px-4 py-4 md:px-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <ul
          role="list"
          class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-6"
          :aria-label="__('Legend')"
        >
          <li
            v-for="item in legend"
            :key="item.label"
            class="flex items-center gap-1.5"
          >
            <span
              class="size-2.5 rounded-sm"
              :style="{ background: `var(--ink-${item.color}-7)` }"
              aria-hidden="true"
            />
            {{ item.label }}
          </li>
        </ul>
        <p v-if="loadError" role="alert" class="text-p-xs text-danger">
          {{ errorText(loadError, __("Couldn't load the calendar.")) }}
        </p>
      </div>

      <div class="min-h-0 flex-1">
        <Calendar
          :events="events"
          :config="calendarConfig"
          @range-change="onRangeChange"
        >
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
import { __ } from "@/translation";
import { Button, Calendar, TabButtons, call, dayjs } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRouter, type RouteLocationRaw } from "vue-router";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
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

interface CalendarData {
  meetings: MeetingEvent[];
  tasks: TaskEvent[];
  can_see_team: boolean;
}

const calendarConfig = {
  defaultMode: "Week",
  isEditMode: false,
  enableShortcuts: false,
  timeFormat: "24h",
  scrollToHour: 8,
  eventIcons: {},
};

// the frappe-ui Calendar's own colour names (it has no red; pink is its closest)
const COLORS = {
  meeting: "blue",
  task: "violet",
  key: "amber",
  overdue: "pink",
};

const legend = [
  { label: __("Teams meeting"), color: COLORS.meeting },
  { label: __("Task due"), color: COLORS.task },
  { label: __("Key task or milestone"), color: COLORS.key },
  { label: __("Overdue task"), color: COLORS.overdue },
];

const router = useRouter();
const scope = ref<"mine" | "team">("mine");
// the week the calendar opens on, until it reports its own range
const range = ref({
  start: dayjs().startOf("week").format("YYYY-MM-DD"),
  end: dayjs().endOf("week").format("YYYY-MM-DD"),
});

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

load();
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
      color: COLORS.meeting,
      kind: "meeting",
      record: m,
    };
  });
  const tasks = (data.value?.tasks ?? []).map((t) => ({
    id: `task:${t.name}`,
    title: t.subject,
    participant: t.project_name || "",
    fromDate: t.exp_end_date,
    toDate: t.exp_end_date,
    isFullDay: true,
    color:
      t.exp_end_date < today
        ? COLORS.overdue
        : t.is_key || t.is_milestone
        ? COLORS.key
        : COLORS.task,
    kind: "task",
    record: t,
  }));
  return [...meetings, ...tasks];
});

function detail(event: Record<string, any>) {
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
