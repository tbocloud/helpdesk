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
            <div class="flex items-center gap-1">
              <Button
                variant="ghost"
                :aria-label="__('Previous {0}', periodNoun)"
                @click="shiftPeriod(-1)"
              >
                <LucideChevronLeft class="size-4" aria-hidden="true" />
              </Button>
              <span
                class="min-w-[10rem] text-center text-base font-medium text-ink-gray-9"
                >{{ periodLabel }}</span
              >
              <Button
                variant="ghost"
                :aria-label="__('Next {0}', periodNoun)"
                @click="shiftPeriod(1)"
              >
                <LucideChevronRight class="size-4" aria-hidden="true" />
              </Button>
              <div class="w-40">
                <FormControl
                  v-model="anchor"
                  type="date"
                  :aria-label="__('Go to date')"
                />
              </div>
              <Button
                v-if="!includesToday"
                variant="ghost"
                :label="__('Today')"
                @click="anchor = today"
              />
            </div>
          </template>
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
            :posts="monthPosts.data ?? []"
            :month="rangeKey"
            :period="period"
            :loading="monthPosts.loading"
            :filters-customer="filters.customer"
            @open="openPost"
            @add="openAdd"
            @action="openAction"
          />
          <ContentSheet
            v-else
            :period="period"
            :posts="monthPosts.data ?? []"
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

      <aside
        class="hidden w-72 shrink-0 flex-col border-l border-outline-gray-2 xl:flex"
        :aria-label="__('Ideas without a date')"
      >
        <div class="flex items-center justify-between px-4 pb-2 pt-4">
          <div
            class="text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
          >
            {{ __("Ideas") }}
          </div>
          <span class="font-mono text-xs tabular-nums text-ink-gray-5">{{
            ideas.data?.length ?? 0
          }}</span>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
          <p
            v-if="!ideas.loading && !ideas.data?.length"
            class="px-2 py-6 text-p-sm text-ink-gray-5"
          >
            {{
              __("No undated ideas. Use Add entry and leave the date empty.")
            }}
          </p>
          <button
            v-for="idea in ideas.data ?? []"
            :key="idea.name"
            type="button"
            class="flex w-full flex-col gap-0.5 rounded-lg px-2 py-2 text-left hover:bg-surface-gray-2 focus-visible:bg-surface-gray-2"
            @click="openPost(idea.name)"
          >
            <span class="truncate text-sm text-ink-gray-9">{{
              idea.title
            }}</span>
            <span class="truncate text-xs text-ink-gray-5"
              >{{ idea.channel }} · {{ idea.customer }}</span
            >
          </button>
        </div>
      </aside>
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
import { useStorage } from "@vueuse/core";
import { computed, markRaw, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideLayoutList from "~icons/lucide/layout-list";
import LucidePlus from "~icons/lucide/plus";
import LucideMail from "~icons/lucide/mail";
import LucideSheet from "~icons/lucide/sheet";
import {
  CHANNELS,
  STATUSES,
  stageColor,
  type ContentPost,
  type EntryAction,
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
const rangeKey = computed(
  () => `${period.value}:${rangeStart.value.format("YYYY-MM-DD")}`
);
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

const filters = reactive({ customer: "", channel: "", status: "" });
const range = ref<{ start: string; end: string } | null>(null);
const hasFilters = computed(
  () => !!(filters.customer || filters.channel || filters.status)
);

function baseFilters() {
  const f: Record<string, unknown> = {};
  if (filters.customer) f.customer = filters.customer;
  if (filters.channel) f.channel = filters.channel;
  // cancelled posts stay off the calendar unless asked for
  f.status = filters.status || ["!=", "Cancelled"];
  return f;
}

const FIELDS = ["name", "title", "status", "channel", "customer", "publish_on"];

const posts = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "HD Content Post",
    fields: FIELDS,
    filters: {
      ...baseFilters(),
      publish_on: ["between", [range.value!.start, range.value!.end]],
    },
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
            rangeStart.value.format("YYYY-MM-DD 00:00:00"),
            rangeEnd.value.format("YYYY-MM-DD 23:59:59"),
          ],
        ],
      },
      order_by: "publish_on asc",
      limit_page_length: 1000,
    };
  },
});

const ideas = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "HD Content Post",
    fields: FIELDS,
    filters: { ...baseFilters(), publish_on: ["is", "not set"] },
    order_by: "creation desc",
    limit_page_length: 200,
  }),
  auto: true,
});

const events = computed(() =>
  (posts.data ?? []).map((p: ContentPost) => {
    const start = dayjs(p.publish_on);
    return {
      id: p.name,
      title: `${p.channel} · ${p.title}`,
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
  ideas.reload();
}

watch(filters, refresh);
watch([view, rangeKey], refresh, { immediate: true });

function clearFilters() {
  Object.assign(filters, { customer: "", channel: "", status: "" });
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
