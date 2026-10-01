<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-1.5 text-lg-medium">
          <button
            v-if="scope.data?.sees_team && employee"
            type="button"
            class="text-ink-gray-5 hover:text-ink-gray-8"
            @click="employee = ''"
          >
            {{ __("Performance") }}
          </button>
          <LucideChevronRight
            v-if="scope.data?.sees_team && employee"
            class="size-4 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="text-ink-gray-9">{{ heading }}</span>
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

      <template v-if="scope.data?.sees_team">
        <div class="mx-1 h-5 w-px bg-outline-gray-2" aria-hidden="true" />
        <div v-if="!employee && scope.data.departments.length" class="w-52">
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
        <div class="w-60">
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
          {{ __("No employee record") }}
        </p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          {{
            __(
              "Your login isn't linked to an active employee, so there is nothing to show yet. Ask HR to set your user on your Employee record."
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
        <EmployeeView v-if="employee" :data="report.data" />
        <TeamView v-else :data="report.data" @select="employee = $event" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import EmployeeView from "./components/EmployeeView.vue";
import TeamView from "./components/TeamView.vue";

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
  if (!employee.value) return __("Team performance");
  const person = scope.data?.employees?.find(
    (e: { employee: string }) => e.employee === employee.value
  );
  return scope.data?.sees_team
    ? person?.employee_name || __("Performance")
    : __("My performance");
});

const params = () => ({ from_date: range.value.from, to_date: range.value.to });
const teamReport = createResource({
  url: "helpdesk.api.performance.get_team_performance",
  makeParams: () => ({ ...params(), department: department.value || null }),
});
const personReport = createResource({
  url: "helpdesk.api.performance.get_employee_performance",
  makeParams: () => ({ ...params(), employee: employee.value }),
});
const report = computed(() => (employee.value ? personReport : teamReport));

function load() {
  if (!scope.data) return;
  if (!scope.data.sees_team && !scope.data.me) return;
  if (!range.value.from || !range.value.to) return;
  report.value.reload();
}

watch(
  [() => scope.data, employee, department, range],
  () => {
    router.replace({
      query: {
        period: preset.value,
        ...(preset.value === "custom"
          ? { from: custom.from, to: custom.to }
          : {}),
        ...(employee.value ? { employee: employee.value } : {}),
        ...(department.value && !employee.value
          ? { department: department.value }
          : {}),
      },
    });
    load();
  },
  { deep: true }
);
</script>
