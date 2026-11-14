<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="view === 'customers' && customer ? undefined : heading"
      :subtitle="
        view === 'customers' && customer
          ? undefined
          : __('How the work went, per customer and per person, for a period.')
      "
    >
      <!-- one customer's report: the way back to the list sits before its name -->
      <template v-if="view === 'customers' && customer" #left-header>
        <div class="flex min-w-0 items-center gap-1.5">
          <button
            type="button"
            class="rounded text-lg-medium text-ink-gray-5 hover:text-ink-gray-8 md:text-xl"
            @click="customer = ''"
          >
            {{ __("Customers") }}
          </button>
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <h1
            class="truncate text-lg font-bold text-ink-gray-9 md:text-[28px] md:leading-[1.2] md:tracking-[-0.02em]"
          >
            {{ heading }}
          </h1>
        </div>
      </template>
    </LayoutHeader>

    <div class="relative min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <!-- the report, then one row of filters that scopes everything below -->
        <div class="flex flex-wrap items-center gap-x-4 gap-y-3">
          <div class="max-w-full overflow-x-auto">
            <ViewTabs
              v-model="view"
              :aria-label="__('Report')"
              :options="
                VIEWS.map((v) => ({
                  label: v.label,
                  value: v.key,
                  icon: v.icon,
                }))
              "
            />
          </div>
          <div
            class="flex flex-wrap items-center gap-2.5"
            role="group"
            :aria-label="__('Filter the report')"
          >
            <div class="w-44">
              <FormControl
                v-model="preset"
                type="select"
                size="md"
                :options="
                  PRESETS.map((p) => ({ label: p.label, value: p.key }))
                "
                :aria-label="__('Period')"
              />
            </div>
            <template v-if="preset === 'custom'">
              <div class="w-40">
                <FormControl
                  v-model="custom.from"
                  type="date"
                  size="md"
                  :aria-label="__('From')"
                />
              </div>
              <span class="text-ink-gray-5">–</span>
              <div class="w-40">
                <FormControl
                  v-model="custom.to"
                  type="date"
                  size="md"
                  :aria-label="__('To')"
                />
              </div>
            </template>
            <span v-else class="text-[13px] tabular-nums text-ink-gray-6">{{
              rangeLabel
            }}</span>

            <div class="w-56">
              <Link
                v-model="forCustomer"
                doctype="HD Customer"
                :placeholder="__('All customers')"
                :aria-label="__('Customer')"
              />
            </div>

            <template v-if="scope.data?.sees_team">
              <div
                v-if="departmentShown && scope.data.departments.length"
                class="w-52"
              >
                <FormControl
                  v-model="department"
                  type="select"
                  size="md"
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
                  size="md"
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
        </div>

        <div
          v-if="scope.data && !scope.data.sees_team && !scope.data.me"
          class="rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-14 text-center"
        >
          <p class="text-base font-semibold text-ink-gray-9">
            {{ __("Nothing to show yet") }}
          </p>
          <p class="mx-auto mt-1 max-w-md text-p-sm text-ink-gray-6">
            {{
              __(
                "Performance covers active helpdesk agents, and your login isn't one. Ask an admin to make you an agent."
              )
            }}
          </p>
        </div>

        <div
          v-else-if="report.error"
          class="flex items-center justify-between gap-3 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {{ report.error.messages?.[0] || __("Couldn't load the report.") }}
          <Button :label="__('Retry')" @click="report.reload()" />
        </div>

        <div
          v-else-if="!report.data"
          class="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4"
          aria-busy="true"
        >
          <div
            v-for="i in 4"
            :key="i"
            class="h-[138px] animate-pulse rounded-xl bg-surface-gray-3"
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
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import ViewTabs from "@/components/ViewTabs.vue";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, markRaw, reactive, ref, watch, type Component } from "vue";
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
const VIEWS: { key: View; label: string; icon: Component }[] = [
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
// one person's report isn't narrowed by department, so the filter hides and
// stops applying; it comes back as it was for the whole team
const departmentShown = computed(
  () => view.value === "customers" || !employee.value
);
const activeDepartment = () =>
  (departmentShown.value && department.value) || null;

const range = computed(() => {
  const today = dayjs();
  const fmt = (d: ReturnType<typeof dayjs>) => d.format("YYYY-MM-DD");
  // weeks run Monday to Sunday, like the report's weekly buckets
  const monday = today.subtract((today.day() + 6) % 7, "day");
  switch (preset.value) {
    case "this_week":
      return { from: fmt(monday), to: fmt(monday.add(6, "day")) };
    case "last_week":
      return {
        from: fmt(monday.subtract(7, "day")),
        to: fmt(monday.subtract(1, "day")),
      };
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
    department: activeDepartment(),
    for_customer: forCustomer.value || null,
  }),
});
const contentReport = createResource({
  url: "helpdesk.api.content_performance.get_content_performance",
  makeParams: () => ({
    ...params(),
    employee: employee.value || null,
    department: activeDepartment(),
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
        ...(activeDepartment() ? { department: activeDepartment() } : {}),
      },
    });
    load();
  },
  { deep: true }
);
</script>
