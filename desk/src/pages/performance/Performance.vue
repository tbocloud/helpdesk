<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-1.5 text-lg-medium">
          <button
            v-if="view === 'customers' && customer"
            type="button"
            class="text-ink-gray-5 hover:text-ink-gray-8"
            @click="customer = ''"
          >
            {{ __("Customers") }}
          </button>
          <LucideChevronRight
            v-if="view === 'customers' && customer"
            class="size-4 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="text-ink-gray-9">{{ heading }}</span>
        </div>
      </template>
      <template #right-header>
        <div
          class="inline-flex rounded-lg bg-surface-gray-2 p-0.5"
          role="tablist"
          :aria-label="__('Report')"
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
                ? 'bg-brand text-brand-on shadow-sm'
                : 'text-ink-gray-6 hover:text-ink-gray-8'
            "
            @click="view = v.key"
          >
            <component :is="v.icon" class="size-4" aria-hidden="true" />
            {{ v.label }}
          </button>
        </div>
      </template>
    </LayoutHeader>

    <!-- one row of filters scopes everything below -->
    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2.5 md:px-5"
    >
      <div class="w-44">
        <FormControl
          v-model="preset"
          type="select"
          :options="PRESETS.map((p) => ({ label: p.label, value: p.key }))"
          :aria-label="__('Period')"
        />
      </div>
      <template v-if="preset === 'custom'">
        <div class="w-40">
          <FormControl
            v-model="custom.from"
            type="date"
            :aria-label="__('From')"
          />
        </div>
        <span class="text-ink-gray-5">–</span>
        <div class="w-40">
          <FormControl v-model="custom.to" type="date" :aria-label="__('To')" />
        </div>
      </template>
      <span v-else class="text-sm text-ink-gray-6">{{ rangeLabel }}</span>

      <div class="mx-1 h-5 w-px bg-outline-gray-2" aria-hidden="true" />
      <div class="w-56">
        <Link
          v-model="forCustomer"
          doctype="HD Customer"
          :placeholder="__('All customers')"
          :aria-label="__('Customer')"
        />
      </div>

      <template v-if="scope.data?.sees_team">
        <div class="mx-1 h-5 w-px bg-outline-gray-2" aria-hidden="true" />
        <div
          v-if="
            (view === 'customers' || !employee) && scope.data.departments.length
          "
          class="w-52"
        >
          <FormControl
            v-model="department"
            type="select"
            :options="[
              { label: __('All departments'), value: '' },
              ...scope.data.departments,
            ]"
            :aria-label="__('Department')"
          />
        </div>
        <div v-if="view === 'content'" class="w-60">
          <FormControl
            v-model="employee"
            type="select"
            :options="[
              { label: __('Whole team'), value: '' },
              ...scope.data.employees.map((e) => ({
                label: e.employee_name,
                value: e.employee,
              })),
            ]"
            :aria-label="__('Employee')"
          />
        </div>
      </template>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto p-4 md:p-5">
      <div
        v-if="scope.data && !scope.data.sees_team && !scope.data.me"
        class="mx-auto max-w-md py-16 text-center"
      >
        <p class="text-base font-medium text-ink-gray-9">
          {{ __("Nothing to show yet") }}
        </p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          {{
            __(
              "Performance covers active helpdesk agents, and your login isn't one. Ask an admin to make you an agent."
            )
          }}
        </p>
      </div>

      <div
        v-else-if="report.error"
        class="flex items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger"
        role="alert"
      >
        {{ report.error.messages?.[0] || __("Couldn't load the report.") }}
        <Button size="sm" :label="__('Retry')" @click="report.reload()" />
      </div>

      <div
        v-else-if="!report.data"
        class="grid grid-cols-2 gap-3 lg:grid-cols-6"
        aria-busy="true"
      >
        <div
          v-for="i in 6"
          :key="i"
          class="h-28 animate-pulse rounded-xl bg-surface-gray-2"
          :class="i === 1 ? 'col-span-2' : ''"
        />
      </div>

      <!-- refetching keeps the last render, dimmed, instead of flashing -->
      <div
        v-else
        class="transition-opacity"
        :class="report.loading ? 'opacity-60' : ''"
      >
        <ContentPerformanceView
          v-if="view === 'content'"
          :data="report.data"
          :period-label="rangeLabel"
          @select="employee = $event"
        />
        <CustomerPerformanceView
          v-else
          :data="report.data"
          :period-label="rangeLabel"
          @select="customer = $event"
          @person="openPerson"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, markRaw, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideBuilding2 from "~icons/lucide/building-2";
import ContentPerformanceView from "./components/ContentPerformanceView.vue";
import CustomerPerformanceView from "./components/CustomerPerformanceView.vue";

type Preset =
  | "this_week"
  | "last_week"
  | "this_month"
  | "last_month"
  | "last_30"
  | "this_quarter"
  | "custom";

const PRESETS: { key: Preset; label: string }[] = [
  { key: "this_week", label: __("This week") },
  { key: "last_week", label: __("Last week") },
  { key: "this_month", label: __("This month") },
  { key: "last_month", label: __("Last month") },
  { key: "last_30", label: __("Last 30 days") },
  { key: "this_quarter", label: __("This quarter") },
  { key: "custom", label: __("Custom range") },
];

const route = useRoute();
const router = useRouter();
const query = (k: string) =>
  typeof route.query[k] === "string" ? (route.query[k] as string) : "";

const preset = ref<Preset>((query("period") as Preset) || "this_month");
const custom = reactive({
  from: query("from") || dayjs().startOf("month").format("YYYY-MM-DD"),
  to: query("to") || dayjs().format("YYYY-MM-DD"),
});
const employee = ref(query("employee"));

type View = "customers" | "content";
const VIEWS: { key: View; label: string; icon: unknown }[] = [
  { key: "customers", label: __("Customers"), icon: markRaw(LucideBuilding2) },
  {
    key: "content",
    label: __("By employee"),
    icon: markRaw(LucideCalendarDays),
  },
];
const view = ref<View>(query("view") === "content" ? "content" : "customers");
const customer = ref(query("customer"));
// limits both tabs to one customer's posts
const forCustomer = ref(query("for_customer"));
watch(forCustomer, (value) => {
  customer.value = value || "";
});
const department = ref(query("department"));

const range = computed(() => {
  const today = dayjs();
  const fmt = (d: ReturnType<typeof dayjs>) => d.format("YYYY-MM-DD");
  switch (preset.value) {
    case "this_week":
      return { from: fmt(today.startOf("week")), to: fmt(today.endOf("week")) };
    case "last_week": {
      const d = today.subtract(1, "week");
      return { from: fmt(d.startOf("week")), to: fmt(d.endOf("week")) };
    }
    case "last_month": {
      const d = today.subtract(1, "month");
      return { from: fmt(d.startOf("month")), to: fmt(d.endOf("month")) };
    }
    case "last_30":
      return { from: fmt(today.subtract(29, "day")), to: fmt(today) };
    case "this_quarter": {
      const start = today
        .month(Math.floor(today.month() / 3) * 3)
        .startOf("month");
      return {
        from: fmt(start),
        to: fmt(start.add(2, "month").endOf("month")),
      };
    }
    case "custom":
      return { from: custom.from, to: custom.to };
    default:
      return {
        from: fmt(today.startOf("month")),
        to: fmt(today.endOf("month")),
      };
  }
});

const rangeLabel = computed(() => {
  const from = dayjs(range.value.from);
  const to = dayjs(range.value.to);
  return from.year() === to.year()
    ? `${from.format("D MMM")} – ${to.format("D MMM YYYY")}`
    : `${from.format("D MMM YYYY")} – ${to.format("D MMM YYYY")}`;
});

const scope = createResource({
  url: "helpdesk.api.performance.get_scope",
  auto: true,
  onSuccess(data) {
    // people without the team view always look at themselves
    if (!data.sees_team) employee.value = data.me || "";
  },
});

const heading = computed(() => {
  if (view.value === "content")
    return scope.data?.sees_team
      ? __("Content performance")
      : __("My content performance");
  if (customer.value) return customer.value;
  return scope.data?.sees_team
    ? __("Performance by customer")
    : __("My customers");
});

function openPerson(person: string) {
  employee.value = person;
  view.value = "content";
}

const params = () => ({ from_date: range.value.from, to_date: range.value.to });
const customerReport = createResource({
  url: "helpdesk.api.content_performance.get_customer_performance",
  makeParams: () => ({
    ...params(),
    customer: customer.value || null,
    department: department.value || null,
    for_customer: forCustomer.value || null,
  }),
});
const contentReport = createResource({
  url: "helpdesk.api.content_performance.get_content_performance",
  makeParams: () => ({
    ...params(),
    employee: employee.value || null,
    department: department.value || null,
    for_customer: forCustomer.value || null,
  }),
});
const report = computed(() =>
  view.value === "content" ? contentReport : customerReport
);

function load() {
  if (!scope.data) return;
  if (!scope.data.sees_team && !scope.data.me) return;
  if (!range.value.from || !range.value.to) return;
  report.value.reload();
}

watch(
  [() => scope.data, employee, customer, forCustomer, department, range, view],
  () => {
    router.replace({
      query: {
        ...(view.value === "content" ? { view: "content" } : {}),
        period: preset.value,
        ...(preset.value === "custom"
          ? { from: custom.from, to: custom.to }
          : {}),
        ...(view.value === "content" && employee.value
          ? { employee: employee.value }
          : {}),
        ...(view.value === "customers" && customer.value
          ? { customer: customer.value }
          : {}),
        ...(forCustomer.value ? { for_customer: forCustomer.value } : {}),
        ...(department.value && (view.value === "customers" || !employee.value)
          ? { department: department.value }
          : {}),
      },
    });
    load();
  },
  { deep: true }
);
</script>
