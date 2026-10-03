<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-1.5 text-lg-medium">
          <router-link
            :to="{ name: 'ContentCalendar' }"
            class="text-ink-gray-5 hover:text-ink-gray-8"
            >{{ __("Content Calendar") }}</router-link
          >
          <LucideChevronRight
            class="size-4 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="text-ink-gray-9">{{ __("Delivery report") }}</span>
        </div>
      </template>
      <template #right-header>
        <Button
          :label="__('Download PDF')"
          :tooltip="
            __(
              'Download this report as a PDF with the current dates and customer'
            )
          "
          :disabled="!rows.length"
          @click="downloadReport('export_pdf')"
        >
          <template #prefix
            ><LucideFileText class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button
          :label="__('Export to Excel')"
          :tooltip="
            __('Download this report with the current dates and customer')
          "
          :disabled="!rows.length"
          @click="downloadReport('export_xlsx')"
        >
          <template #prefix
            ><LucideDownload class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div
      class="flex flex-wrap items-end gap-3 border-b border-outline-gray-2 px-4 py-3 md:px-5"
    >
      <div class="w-40">
        <FormControl
          v-model="filters.from_date"
          type="date"
          :label="__('From')"
        />
      </div>
      <div class="w-40">
        <FormControl v-model="filters.to_date" type="date" :label="__('To')" />
      </div>
      <div class="w-full sm:w-60">
        <Link
          v-model="filters.customer"
          doctype="HD Customer"
          :label="__('Customer')"
          :placeholder="__('All customers')"
        />
      </div>
      <span class="pb-1.5 text-sm text-ink-gray-5">{{ periodLabel }}</span>
    </div>

    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <div
          v-if="report.error"
          class="flex items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {{ report.error?.messages?.[0] || __("Couldn't load the report.") }}
          <Button size="sm" :label="__('Retry')" @click="report.reload()" />
        </div>

        <div
          v-else-if="report.loading && !report.data"
          class="grid grid-cols-1 gap-4 lg:grid-cols-3"
          aria-busy="true"
        >
          <div
            v-for="i in 3"
            :key="i"
            class="h-56 animate-pulse rounded-xl bg-surface-gray-2"
          />
        </div>

        <p
          v-else-if="!rows.length"
          class="rounded-xl border border-dashed border-outline-gray-3 px-4 py-16 text-center text-p-sm text-ink-gray-5"
        >
          {{ __("No posts planned in this period.") }}
        </p>

        <div
          v-else
          class="flex flex-col gap-4 transition-opacity"
          :class="report.loading ? 'opacity-60' : ''"
        >
          <!-- the headline: how delivery went, at a glance -->
          <section
            class="grid grid-cols-1 gap-5 rounded-xl border border-outline-gray-2 bg-surface-base p-5 lg:grid-cols-[auto_minmax(0,1fr)]"
          >
            <div class="flex flex-wrap items-center gap-6">
              <DeliveryDonut
                :counts="segments"
                :center="pctText(pct(total.on_time + total.late, due))"
                :caption="__('delivered')"
              />
              <div class="flex min-w-[12rem] flex-col gap-3">
                <div>
                  <h2 class="text-base font-semibold text-ink-gray-9">
                    {{ __("Delivery health") }}
                  </h2>
                  <p class="text-p-sm text-ink-gray-5">
                    {{
                      __(
                        "{0} of {1} posts due are published",
                        String(total.published),
                        String(due)
                      )
                    }}
                  </p>
                </div>
                <ul class="flex flex-col gap-1.5" :aria-label="__('Legend')">
                  <li
                    v-for="s in SEGMENTS"
                    :key="s.key"
                    class="grid grid-cols-[auto_1fr_auto_auto] items-center gap-2 text-sm"
                  >
                    <span
                      class="size-2.5 rounded-sm"
                      :class="s.dot"
                      aria-hidden="true"
                    />
                    <span class="text-ink-gray-7">{{ s.label }}</span>
                    <b class="font-semibold tabular-nums text-ink-gray-9">{{
                      segments[s.key]
                    }}</b>
                    <span
                      class="w-10 text-right text-xs tabular-nums text-ink-gray-5"
                      >{{ pctText(pct(segments[s.key], total.planned)) }}</span
                    >
                  </li>
                </ul>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
              <div
                v-for="k in kpis"
                :key="k.label"
                class="flex items-start gap-3 rounded-lg p-3"
                :class="k.bg"
              >
                <span
                  class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-base"
                  :class="k.ink"
                  aria-hidden="true"
                >
                  <component :is="k.icon" class="size-[18px]" />
                </span>
                <div class="min-w-0">
                  <div class="text-xs font-medium" :class="k.ink">
                    {{ k.label }}
                  </div>
                  <div
                    class="text-2xl font-semibold leading-tight tabular-nums text-ink-gray-9"
                  >
                    {{ k.value }}
                  </div>
                  <div class="truncate text-xs text-ink-gray-6">
                    {{ k.sub }}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <section
              class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 xl:col-span-2"
            >
              <header
                class="mb-3 flex flex-wrap items-start justify-between gap-2"
              >
                <div>
                  <h2 class="text-base font-semibold text-ink-gray-9">
                    {{ __("Delivery by customer") }}
                  </h2>
                  <p class="text-p-sm text-ink-gray-5">
                    {{ __("Every planned post, split by how it went") }}
                  </p>
                </div>
                <ul
                  class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-gray-6"
                  :aria-label="__('Legend')"
                >
                  <li
                    v-for="s in SEGMENTS"
                    :key="s.key"
                    class="flex items-center gap-1.5"
                  >
                    <span
                      class="size-2.5 rounded-sm"
                      :class="s.dot"
                      aria-hidden="true"
                    />
                    {{ s.label }}
                  </li>
                </ul>
              </header>
              <DeliveryByCustomerChart
                :rows="chartRows"
                :selected="filters.customer || null"
                @select="filters.customer = $event"
              />
            </section>

            <section
              class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
            >
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __("Where posts are now") }}
              </h2>
              <p class="mb-4 text-p-sm text-ink-gray-5">
                {{ __("Planned posts by workflow stage") }}
              </p>
              <ul class="flex flex-col gap-4">
                <li v-for="s in stages" :key="s.key">
                  <div class="mb-1.5 flex items-center gap-2 text-sm">
                    <span
                      class="flex size-6 items-center justify-center rounded-md"
                      :class="[s.bg, s.ink]"
                      aria-hidden="true"
                    >
                      <component :is="s.icon" class="size-3.5" />
                    </span>
                    <span class="flex-1 text-ink-gray-8">{{ s.label }}</span>
                    <b class="font-semibold tabular-nums text-ink-gray-9">{{
                      s.count
                    }}</b>
                    <span
                      class="w-10 text-right text-xs tabular-nums text-ink-gray-5"
                      >{{ pctText(pct(s.count, total.planned)) }}</span
                    >
                  </div>
                  <div
                    class="h-2 overflow-hidden rounded-full bg-surface-gray-2"
                    role="meter"
                    :aria-valuenow="s.count"
                    aria-valuemin="0"
                    :aria-valuemax="total.planned"
                    :aria-label="s.label"
                  >
                    <div
                      class="h-full rounded-full"
                      :class="s.fill"
                      :style="{
                        width: `${pct(s.count, total.planned) ?? 0}%`,
                      }"
                    />
                  </div>
                  <p class="mt-1 text-xs text-ink-gray-5">{{ s.hint }}</p>
                </li>
              </ul>
            </section>
          </div>

          <!-- per customer, with a health call -->
          <section
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <header class="p-4">
              <h2 class="text-base font-semibold text-ink-gray-9">
                {{ __("Customers") }}
              </h2>
              <p class="text-p-sm text-ink-gray-5">
                {{ __("Click a customer to see only their numbers") }}
              </p>
            </header>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[900px] text-sm">
                <thead
                  class="border-y border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
                >
                  <tr>
                    <th scope="col" class="px-4 py-2.5 text-left font-medium">
                      {{ __("Customer") }}
                    </th>
                    <th scope="col" class="px-3 py-2.5 text-left font-medium">
                      {{ __("Health") }}
                    </th>
                    <th
                      scope="col"
                      class="w-56 px-3 py-2.5 text-left font-medium"
                    >
                      {{ __("Delivery") }}
                    </th>
                    <th
                      v-for="col in NUMERIC"
                      :key="col.key"
                      scope="col"
                      class="whitespace-nowrap px-3 py-2.5 text-right font-medium"
                    >
                      {{ col.label }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in rows"
                    :key="row.customer"
                    class="cursor-pointer border-b border-outline-gray-1 last:border-0"
                    :class="
                      row.customer === filters.customer
                        ? 'bg-brand-soft'
                        : 'hover:bg-surface-gray-1'
                    "
                    tabindex="0"
                    @click="toggleCustomer(row.customer)"
                    @keydown.enter="toggleCustomer(row.customer)"
                  >
                    <td class="px-4 py-3 font-medium text-ink-gray-9">
                      {{ row.customer }}
                    </td>
                    <td class="px-3 py-3">
                      <span
                        class="inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2 text-xs font-medium"
                        :class="health(row).classes"
                      >
                        <component
                          :is="health(row).icon"
                          class="size-3.5"
                          aria-hidden="true"
                        />
                        {{ health(row).label }}
                      </span>
                    </td>
                    <td class="px-3 py-3">
                      <div
                        class="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-gray-2"
                        role="img"
                        :aria-label="segmentLabel(row)"
                        :title="segmentLabel(row)"
                      >
                        <div
                          v-for="s in SEGMENTS"
                          :key="s.key"
                          :class="s.dot"
                          :style="{
                            width: `${
                              row.planned
                                ? (rowSegment(row, s.key) / row.planned) * 100
                                : 0
                            }%`,
                          }"
                        />
                      </div>
                    </td>
                    <td
                      v-for="col in NUMERIC"
                      :key="col.key"
                      class="px-3 py-3 text-right tabular-nums"
                    >
                      <span
                        v-if="col.tone && col.tone(row)"
                        class="inline-block min-w-[2rem] rounded-md px-1.5 py-0.5 text-center font-semibold"
                        :class="col.tone(row)"
                        >{{ col.format(row) }}</span
                      >
                      <span v-else class="text-ink-gray-8">{{
                        col.format(row)
                      }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import DeliveryByCustomerChart from "@/pages/performance/components/DeliveryByCustomerChart.vue";
import type { Timing } from "@/pages/performance/performanceMeta";
import { __ } from "@/translation";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, watch } from "vue";
import LucideCalendarCheck from "~icons/lucide/calendar-check";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideDownload from "~icons/lucide/download";
import LucideEye from "~icons/lucide/eye";
import LucideFileText from "~icons/lucide/file-text";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLightbulb from "~icons/lucide/lightbulb";
import LucideSend from "~icons/lucide/send";
import LucideTimer from "~icons/lucide/timer";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import DeliveryDonut from "./components/DeliveryDonut.vue";

interface Row {
  customer: string;
  // from the customer's monthly package; null when it has none
  promised: number | null;
  planned: number;
  published: number;
  on_time: number;
  on_time_pct: number;
  late: number;
  overdue: number;
  upcoming: number;
  awaiting_client: number;
  avg_approval_hours: number | null;
  stages: Record<"planning" | "review" | "ready" | "published", number>;
}

// the four ways a planned post can stand; they add up to the plan
const SEGMENTS: { key: Timing; label: string; dot: string }[] = [
  { key: "On time", label: __("Published on time"), dot: "bg-success" },
  { key: "Late", label: __("Published late"), dot: "bg-warning" },
  { key: "Missed", label: __("Overdue"), dot: "bg-danger" },
  { key: "Upcoming", label: __("Not due yet"), dot: "bg-surface-gray-5" },
];

const pct = (part: number, whole: number) =>
  whole ? Math.round((part / whole) * 100) : null;
const pctText = (v: number | null) => (v == null ? "—" : `${v}%`);

function rowSegment(row: Row, key: Timing) {
  return {
    "On time": row.on_time,
    Late: row.late ?? row.published - row.on_time,
    Missed: row.overdue,
    Upcoming: row.upcoming ?? 0,
  }[key];
}
const segmentLabel = (row: Row) =>
  SEGMENTS.map((s) => `${s.label}: ${rowSegment(row, s.key)}`).join(", ");

function onTimeTone(row: Row) {
  if (!row.published) return "";
  if (row.on_time_pct >= 80) return "bg-success-soft text-success";
  if (row.on_time_pct >= 50) return "bg-warning-soft text-warning";
  return "bg-danger-soft text-danger";
}

const NUMERIC: {
  key: string;
  label: string;
  format: (r: Row) => string;
  tone?: (r: Row) => string;
}[] = [
  {
    key: "promised",
    label: __("Promised"),
    format: (r) => (r.promised == null ? "—" : String(r.promised)),
  },
  {
    key: "planned",
    label: __("Planned"),
    format: (r) => String(r.planned),
    // fewer posts planned than the package promises
    tone: (r) =>
      r.promised != null && r.planned < r.promised
        ? "bg-warning-soft text-warning"
        : "",
  },
  {
    key: "published",
    label: __("Published"),
    format: (r) => String(r.published),
  },
  {
    key: "on_time_pct",
    label: __("On time"),
    format: (r) => (r.published ? `${Math.round(r.on_time_pct)}%` : "—"),
    tone: onTimeTone,
  },
  {
    key: "overdue",
    label: __("Overdue"),
    format: (r) => String(r.overdue),
    tone: (r) => (r.overdue ? "bg-danger-soft text-danger" : ""),
  },
  {
    key: "awaiting_client",
    label: __("Awaiting client"),
    format: (r) => String(r.awaiting_client),
    tone: (r) => (r.awaiting_client ? "bg-warning-soft text-warning" : ""),
  },
  {
    key: "avg_approval_hours",
    label: __("Avg approval"),
    format: (r) =>
      r.avg_approval_hours == null ? "—" : `${r.avg_approval_hours} h`,
  },
];

function health(row: Row) {
  const due = row.planned - (row.upcoming ?? 0);
  if (!due)
    return {
      label: __("Nothing due yet"),
      classes: "bg-surface-gray-2 text-ink-gray-6",
      icon: LucideHourglass,
    };
  if (row.overdue / due >= 0.5)
    return {
      label: __("Behind"),
      classes: "bg-danger-soft text-danger",
      icon: LucideCircleAlert,
    };
  if (row.overdue || row.on_time_pct < 80)
    return {
      label: __("At risk"),
      classes: "bg-warning-soft text-warning",
      icon: LucideTriangleAlert,
    };
  return {
    label: __("On track"),
    classes: "bg-success-soft text-success",
    icon: LucideCircleCheck,
  };
}

const filters = reactive({
  from_date: dayjs().startOf("month").format("YYYY-MM-DD"),
  to_date: dayjs().endOf("month").format("YYYY-MM-DD"),
  customer: "",
});

const periodLabel = computed(() => {
  const from = dayjs(filters.from_date);
  const to = dayjs(filters.to_date);
  if (!from.isValid() || !to.isValid()) return "";
  return `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`;
});

// Frappe's report API checks the report's roles, so this works without desk access
const report = createResource({
  url: "frappe.desk.query_report.run",
  makeParams: () => ({
    report_name: "Content Delivery",
    filters: {
      from_date: filters.from_date,
      to_date: filters.to_date,
      ...(filters.customer ? { customer: filters.customer } : {}),
    },
  }),
  auto: true,
});

watch(filters, () => report.reload());

function toggleCustomer(customer: string) {
  filters.customer = filters.customer === customer ? "" : customer;
}

function downloadReport(method: "export_xlsx" | "export_pdf") {
  const params = new URLSearchParams({
    from_date: filters.from_date,
    to_date: filters.to_date,
  });
  if (filters.customer) params.set("customer", filters.customer);
  window.open(
    `/api/method/helpdesk.helpdesk.report.content_delivery.content_delivery.${method}?${params}`,
    "_blank"
  );
}

// the report adds a total row; the headline shows totals instead
const rows = computed<Row[]>(() =>
  (report.data?.result ?? []).filter(
    (r: any) => r && !Array.isArray(r) && r.customer
  )
);

const total = computed(() => {
  const sum = (fn: (r: Row) => number) =>
    rows.value.reduce((n, r) => n + (fn(r) || 0), 0);
  return {
    planned: sum((r) => r.planned),
    published: sum((r) => r.published),
    on_time: sum((r) => r.on_time),
    late: sum((r) => rowSegment(r, "Late")),
    overdue: sum((r) => r.overdue),
    upcoming: sum((r) => r.upcoming ?? 0),
    awaiting: sum((r) => r.awaiting_client),
    stages: {
      planning: sum((r) => r.stages?.planning),
      review: sum((r) => r.stages?.review),
      ready: sum((r) => r.stages?.ready),
      published: sum((r) => r.stages?.published),
    },
  };
});
const due = computed(() => total.value.planned - total.value.upcoming);

const segments = computed<Record<Timing, number>>(() => ({
  "On time": total.value.on_time,
  Late: total.value.late,
  Missed: total.value.overdue,
  Upcoming: total.value.upcoming,
}));

// approval time weighted by each customer's posts, not a plain average of averages
const avgApproval = computed(() => {
  const timed = rows.value.filter((r) => r.avg_approval_hours != null);
  const weight = timed.reduce((n, r) => n + r.planned, 0);
  if (!weight) return null;
  const hours =
    timed.reduce(
      (n, r) => n + (r.avg_approval_hours as number) * r.planned,
      0
    ) / weight;
  return Math.round(hours * 10) / 10;
});

const kpis = computed(() => [
  {
    label: __("Planned"),
    value: String(total.value.planned),
    sub: __("{0} customers", String(rows.value.length)),
    icon: LucideCalendarCheck,
    bg: "bg-info-soft",
    ink: "text-info",
  },
  {
    label: __("Published"),
    value: String(total.value.published),
    sub: __("{0} of posts due", pctText(pct(total.value.published, due.value))),
    icon: LucideSend,
    bg: "bg-success-soft",
    ink: "text-success",
  },
  {
    label: __("On time"),
    value: pctText(pct(total.value.on_time, total.value.published)),
    sub: __("{0} published late", String(total.value.late)),
    icon: LucideCircleCheck,
    bg: "bg-brand-soft",
    ink: "text-brand-ink",
  },
  {
    label: __("Overdue"),
    value: String(total.value.overdue),
    sub: total.value.overdue
      ? __("due and not published")
      : __("nothing overdue"),
    icon: LucideCircleAlert,
    bg: total.value.overdue ? "bg-danger-soft" : "bg-surface-gray-1",
    ink: total.value.overdue ? "text-danger" : "text-ink-gray-6",
  },
  {
    label: __("Awaiting client"),
    value: String(total.value.awaiting),
    sub: __("in client review now"),
    icon: LucideEye,
    bg: "bg-warning-soft",
    ink: "text-warning",
  },
  {
    label: __("Avg approval"),
    value: avgApproval.value == null ? "—" : `${avgApproval.value} h`,
    sub: __("sent to client → decision"),
    icon: LucideTimer,
    bg: "bg-surface-gray-1",
    ink: "text-ink-gray-7",
  },
]);

const stages = computed(() => [
  {
    key: "planning",
    label: __("Planning"),
    hint: __("Idea, drafting or design"),
    count: total.value.stages.planning,
    icon: LucideLightbulb,
    bg: "bg-info-soft",
    ink: "text-info",
    fill: "bg-info",
  },
  {
    key: "review",
    label: __("In review"),
    hint: __("Internal or client review, or changes asked"),
    count: total.value.stages.review,
    icon: LucideEye,
    bg: "bg-warning-soft",
    ink: "text-warning",
    fill: "bg-warning",
  },
  {
    key: "ready",
    label: __("Ready"),
    hint: __("Approved or scheduled"),
    count: total.value.stages.ready,
    icon: LucideCalendarCheck,
    bg: "bg-brand-soft",
    ink: "text-brand-ink",
    fill: "bg-brand",
  },
  {
    key: "published",
    label: __("Published"),
    hint: __("Live on the channel"),
    count: total.value.stages.published,
    icon: LucideSend,
    bg: "bg-success-soft",
    ink: "text-success",
    fill: "bg-success",
  },
]);

const chartRows = computed(() =>
  rows.value.map((r) => ({
    customer: r.customer,
    posts: r.planned,
    on_time: r.on_time,
    published: r.published,
    missed: r.overdue,
    upcoming: r.upcoming ?? 0,
  }))
);
</script>
