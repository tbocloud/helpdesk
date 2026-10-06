<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Content Calendar") }}
        </div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :label="__('Send portal email')"
          @click="shareOpen = true"
        >
          <template #prefix
            ><LucideMail class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button
          variant="ghost"
          :label="__('Delivery report')"
          :route="{ name: 'ContentReport' }"
        >
          <template #prefix
            ><LucideChartColumn class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button variant="solid" :label="__('Add entry')" @click="openAdd()">
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2.5 md:px-5"
    >
      <Link
        v-model="filters.customer"
        doctype="HD Customer"
        class="w-full sm:w-56"
        :placeholder="__('All customers')"
      />
      <div class="w-40">
        <FormControl
          v-model="filters.channel"
          type="select"
          :options="[{ label: __('All channels'), value: '' }, ...CHANNELS]"
          :aria-label="__('Channel')"
        />
      </div>
      <div class="w-44">
        <FormControl
          v-model="filters.status"
          type="select"
          :options="[{ label: __('All statuses'), value: '' }, ...STATUSES]"
          :aria-label="__('Status')"
        />
      </div>
      <div class="w-full sm:w-56">
        <Link
          v-model="filters.person"
          doctype="User"
          :filters="{ enabled: 1, user_type: 'System User' }"
          :placeholder="__('Everyone')"
          :aria-label="__('Person')"
        />
      </div>
      <Button
        :variant="filters.person === authStore.userId ? 'subtle' : 'ghost'"
        :label="__('My posts')"
        :title="
          __('Posts where I am the writer, designer, marketer or video editor')
        "
        @click="
          filters.person =
            filters.person === authStore.userId ? '' : authStore.userId
        "
      >
        <template #prefix
          ><LucideUser class="size-4" aria-hidden="true"
        /></template>
      </Button>
      <Button
        v-if="hasFilters"
        variant="ghost"
        :label="__('Clear')"
        @click="clearFilters"
      />
      <div class="flex-1" />
      <div
        v-if="view === 'calendar'"
        class="hidden items-center gap-3 text-xs text-ink-gray-5 lg:flex"
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
    </div>

    <div class="flex min-h-0 flex-1">
      <div class="relative flex min-w-0 flex-1 flex-col gap-3 p-3 md:p-4">
        <div class="flex flex-wrap items-center gap-2">
          <div
            class="inline-flex rounded-lg bg-surface-gray-2 p-0.5"
            role="tablist"
            :aria-label="__('View')"
          >
            <button
              v-for="v in VIEWS"
              :key="v.key"
              type="button"
              role="tab"
              :aria-selected="view === v.key"
              class="inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-sm"
              :class="
                view === v.key
                  ? 'bg-surface-base text-ink-gray-9 shadow-sm'
                  : 'text-ink-gray-6 hover:text-ink-gray-8'
              "
              @click="view = v.key"
            >
              <component :is="v.icon" class="size-4" aria-hidden="true" />
              {{ v.label }}
            </button>
          </div>
          <template v-if="view !== 'calendar'">
            <div class="flex items-center gap-1">
              <Button
                :label="__('Today')"
                :disabled="includesToday"
                :tooltip="__('Go to today (T)')"
                @click="anchor = today"
              />
              <Button
                variant="ghost"
                :aria-label="__('Previous {0}', periodNoun)"
                :tooltip="__('Previous {0} (←)', periodNoun)"
                @click="shiftPeriod(-1)"
              >
                <LucideChevronLeft class="size-4" aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                :aria-label="__('Next {0}', periodNoun)"
                :tooltip="__('Next {0} (→)', periodNoun)"
                @click="shiftPeriod(1)"
              >
                <LucideChevronRight class="size-4" aria-hidden="true" />
              </Button>
              <!-- the label opens the browser's date picker -->
              <label
                class="relative inline-flex h-8 cursor-pointer items-center gap-1 rounded-md px-2 text-base font-medium text-ink-gray-9 hover:bg-surface-gray-2 focus-within:ring-2 focus-within:ring-outline-gray-3"
                :title="__('Pick a date')"
                @click.prevent="openDatePicker"
              >
                {{ periodLabel }}
                <LucideChevronDown
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
                <input
                  ref="dateInput"
                  v-model="anchor"
                  type="date"
                  class="absolute inset-0 opacity-0 pointer-events-none"
                  :aria-label="__('Go to date')"
                  tabindex="-1"
                />
              </label>
            </div>
            <div class="flex-1" />
            <div
              class="inline-flex rounded-lg bg-surface-gray-2 p-0.5"
              role="tablist"
              :aria-label="__('Period')"
            >
              <button
                v-for="p in PERIODS"
                :key="p.key"
                type="button"
                role="tab"
                :aria-selected="period === p.key"
                class="h-7 rounded-md px-3 text-sm"
                :class="
                  period === p.key
                    ? 'bg-surface-base text-ink-gray-9 shadow-sm'
                    : 'text-ink-gray-6 hover:text-ink-gray-8'
                "
                @click="period = p.key"
              >
                {{ p.label }}
              </button>
            </div>
          </template>
        </div>
        <div
          v-if="view !== 'calendar' && period !== 'month'"
          class="grid grid-cols-7 gap-1.5"
          role="group"
          :aria-label="__('Days of the week')"
        >
          <button
            v-for="d in weekDays"
            :key="d.date"
            type="button"
            class="flex flex-col items-center gap-0.5 rounded-lg border px-1 py-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
            :class="
              period === 'day' && d.date === anchor
                ? 'border-brand bg-brand-soft text-brand-ink'
                : 'border-outline-gray-2 bg-surface-base text-ink-gray-7 hover:bg-surface-gray-2'
            "
            :aria-pressed="period === 'day' && d.date === anchor"
            :aria-label="d.ariaLabel"
            @click="openDay(d.date)"
          >
            <span class="text-2xs uppercase tracking-[0.06em]">{{
              d.weekday
            }}</span>
            <span
              class="grid size-7 place-items-center rounded-full text-base font-semibold tabular-nums"
              :class="d.date === today ? 'bg-brand text-brand-on' : ''"
              >{{ d.day }}</span
            >
            <span class="flex h-4 items-center gap-1 text-xs tabular-nums">
              <span
                v-if="d.missed"
                class="size-1.5 rounded-full bg-danger"
                aria-hidden="true"
              />
              <span v-if="d.count" class="font-mono">{{ d.count }}</span>
              <span v-else class="text-ink-gray-4">–</span>
            </span>
          </button>
        </div>
        <div
          v-if="(view === 'calendar' ? posts : monthPosts).error"
          class="absolute inset-x-4 top-4 z-10 flex items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger"
          role="alert"
        >
          {{ __("Couldn't load posts.") }}
          <Button size="sm" :label="__('Retry')" @click="refresh()" />
        </div>
        <div v-if="view !== 'calendar'" class="min-h-0 flex-1 overflow-y-auto">
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
  FormControl,
  toast,
} from "frappe-ui";
import { useEventListener, useStorage } from "@vueuse/core";
import { computed, markRaw, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideLayoutList from "~icons/lucide/layout-list";
import LucidePlus from "~icons/lucide/plus";
import LucideMail from "~icons/lucide/mail";
import LucideSheet from "~icons/lucide/sheet";
import LucideUser from "~icons/lucide/user";
import { useAuthStore } from "@/stores/auth";
import {
  CHANNELS,
  type ContentPost,
  type EntryAction,
  isMissed,
  platformsOf,
  stageColor,
  STATUSES,
  TEAM_ROLES,
  type TeamRole,
} from "./constants";
import AddEntryDialog from "./components/AddEntryDialog.vue";
import ContentBoard from "./components/ContentBoard.vue";
import ContentSheet from "./components/ContentSheet.vue";
import EntryActionDialog from "./components/EntryActionDialog.vue";
import PostDialog from "./components/PostDialog.vue";
import SharePortalDialog from "./components/SharePortalDialog.vue";

const calendarConfig = {
  defaultMode: "Month",
  disableModes: ["Day"],
  isEditMode: true,
  enableShortcuts: false,
  timeFormat: "12h",
  eventIcons: {},
};

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
    return {
      date,
      weekday: day.format("ddd"),
      day: day.format("D"),
      count: onDay.length,
      missed,
      ariaLabel: `${day.format("dddd D MMMM")}: ${onDay.length} ${
        onDay.length === 1 ? __("post") : __("posts")
      }${missed ? `, ${__("some missed")}` : ""}`,
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
    target?.closest("input, textarea, select, [contenteditable], [role=dialog]")
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

const authStore = useAuthStore();
const filters = reactive({ customer: "", channel: "", status: "", person: "" });
const range = ref<{ start: string; end: string } | null>(null);
const hasFilters = computed(
  () =>
    !!(filters.customer || filters.channel || filters.status || filters.person)
);

/** Posts the chosen person is on, in any role, as main person or one of several. */
function personFilters() {
  const u = filters.person;
  if (!u) return undefined;
  return [
    ...TEAM_ROLES.map((r) => [r.field, "=", u]),
    ["HD Content Post Member", "user", "=", u],
  ];
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
    or_filters: personFilters(),
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
      or_filters: personFilters(),
      order_by: "publish_on asc",
      limit_page_length: 1000,
    };
  },
});

const events = computed(() =>
  (posts.data ?? []).map((p: ContentPost) => {
    const start = dayjs(p.publish_on);
    return {
      id: p.name,
      title: `${platformsOf(p).join(", ")} · ${p.title}`,
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

function refresh() {
  if (view.value === "calendar") {
    if (range.value) posts.reload();
  } else {
    monthPosts.reload();
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

function openAdd(date?: string) {
  addDate.value = date || "";
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
