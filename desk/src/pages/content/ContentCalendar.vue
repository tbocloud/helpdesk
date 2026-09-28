<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Content Calendar") }}</div>
      </template>
      <template #right-header>
        <Button variant="solid" :label="__('New post')" @click="openNew()">
          <template #prefix><LucidePlus class="size-4" aria-hidden="true" /></template>
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
      <FormControl
        v-model="filters.channel"
        type="select"
        class="w-40"
        :options="[{ label: __('All channels'), value: '' }, ...CHANNELS]"
        :aria-label="__('Channel')"
      />
      <FormControl
        v-model="filters.status"
        type="select"
        class="w-44"
        :options="[{ label: __('All statuses'), value: '' }, ...STATUSES]"
        :aria-label="__('Status')"
      />
      <Button
        v-if="hasFilters"
        variant="ghost"
        :label="__('Clear')"
        @click="clearFilters"
      />
      <div class="flex-1" />
      <div
        class="hidden items-center gap-3 text-xs text-ink-gray-5 lg:flex"
        aria-hidden="true"
      >
        <span v-for="s in legend" :key="s.label" class="flex items-center gap-1.5">
          <span class="size-2 rounded-sm" :class="s.swatch" />{{ s.label }}
        </span>
      </div>
    </div>

    <div class="flex min-h-0 flex-1">
      <div class="relative min-w-0 flex-1 p-3 md:p-4">
        <div
          v-if="posts.error"
          class="absolute inset-x-4 top-4 z-10 flex items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger"
          role="alert"
        >
          {{ __("Couldn't load posts.") }}
          <Button size="sm" :label="__('Retry')" @click="posts.reload()" />
        </div>
        <Calendar
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
          <div class="text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5">
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
            {{ __("No undated ideas. Jot one down with New post — no date needed.") }}
          </p>
          <button
            v-for="idea in ideas.data ?? []"
            :key="idea.name"
            type="button"
            class="flex w-full flex-col gap-0.5 rounded-lg px-2 py-2 text-left hover:bg-surface-gray-2 focus-visible:bg-surface-gray-2"
            @click="openPost(idea.name)"
          >
            <span class="truncate text-sm text-ink-gray-9">{{ idea.title }}</span>
            <span class="truncate text-xs text-ink-gray-5"
              >{{ idea.channel }} · {{ idea.customer }}</span
            >
          </button>
        </div>
      </aside>
    </div>

    <PostDialog v-model:open="dialogOpen" :post="selectedPost" @saved="refresh" />
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
import { computed, reactive, ref, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import { CHANNELS, STATUSES, stageColor } from "./constants";
import PostDialog from "./components/PostDialog.vue";

interface Post {
  name: string;
  title: string;
  status: string;
  channel: string;
  customer: string;
  publish_on?: string;
}

const calendarConfig = {
  defaultMode: "Month",
  disableModes: ["Day"],
  isEditMode: true,
  enableShortcuts: false,
  timeFormat: "24h",
  eventIcons: {},
};

const legend = [
  { label: __("Planning"), swatch: "bg-info" },
  { label: __("In review"), swatch: "bg-warning" },
  { label: __("Approved"), swatch: "bg-brand" },
  { label: __("Published"), swatch: "bg-success" },
];

const filters = reactive({ customer: "", channel: "", status: "" });
const range = ref<{ start: string; end: string } | null>(null);
const hasFilters = computed(() => !!(filters.customer || filters.channel || filters.status));

function baseFilters() {
  const f: Record<string, unknown> = {};
  if (filters.customer) f.customer = filters.customer;
  if (filters.channel) f.channel = filters.channel;
  if (filters.status) f.status = filters.status;
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
  (posts.data ?? []).map((p: Post) => {
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

function onRangeChange({ startDate, endDate }: { startDate: string; endDate: string }) {
  range.value = {
    start: dayjs(startDate).startOf("day").format("YYYY-MM-DD HH:mm:ss"),
    end: dayjs(endDate).endOf("day").format("YYYY-MM-DD HH:mm:ss"),
  };
  posts.reload();
}

function refresh() {
  if (range.value) posts.reload();
  ideas.reload();
}

watch(filters, refresh);

function clearFilters() {
  Object.assign(filters, { customer: "", channel: "", status: "" });
}

// Dragging a post to another day or time reschedules it; roll back if the server refuses
async function onReschedule(event: { id?: string | number; fromDate?: string; fromTime?: string }) {
  const publishOn = dayjs(`${event.fromDate} ${event.fromTime || "10:00"}`).format(
    "YYYY-MM-DD HH:mm:ss"
  );
  try {
    await call("frappe.client.set_value", {
      doctype: "HD Content Post",
      name: String(event.id),
      fieldname: "publish_on",
      value: publishOn,
    });
    toast.success(__("Rescheduled to {0}", dayjs(publishOn).format("D MMM, HH:mm")));
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't reschedule this post"));
  } finally {
    posts.reload();
  }
}

// --- dialog ---

const dialogOpen = ref(false);
const selectedPost = ref<{ name?: string; publish_on?: string } | null>(null);

function openPost(name: string) {
  selectedPost.value = { name };
  dialogOpen.value = true;
}

function openNew(publishOn?: string) {
  selectedPost.value = publishOn ? { publish_on: publishOn } : null;
  dialogOpen.value = true;
}

function onCellClick({ date, time }: { date: Date | string; time: string }) {
  openNew(dayjs(`${dayjs(date).format("YYYY-MM-DD")} ${time || "10:00"}`).format("YYYY-MM-DD HH:mm"));
}
</script>
