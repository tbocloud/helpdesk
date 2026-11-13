<template>
  <SettingsLayoutBase
    :title="form.dashboard_name || __('Dashboard')"
    :back-label="__('Back to CRM dashboards')"
    :dirty="dirty"
    :saving="saving"
    :loading="config.loading && !config.data"
    :error="config.error"
    @retry="config.reload()"
    @back="back"
    @save="save"
  >
    <template #header-actions>
      <Switch v-model="form.is_active" size="sm" :label="__('Active')" />
      <Button
        variant="ghost"
        :label="__('Open dashboard')"
        :disabled="dirty"
        :title="dirty ? __('Save your changes first.') : undefined"
        @click="preview"
      >
        <template #prefix>
          <LucideExternalLink class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #content>
      <div v-if="config.data" class="flex flex-col">
        <SettingsSection :title="__('Details')">
          <FormControl
            v-model="form.dashboard_name"
            :label="__('Name')"
            maxlength="140"
            required
          />
          <FormControl
            v-model="form.description"
            type="textarea"
            :rows="2"
            :label="__('Description')"
            :description="__('Shown to admins in the list.')"
          />
          <Switch
            v-model="form.is_default"
            :label="__('Default dashboard')"
            :description="
              __('Opens first for people who can see more than one.')
            "
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Who sees it')"
          :description="
            __(
              'System Managers and Agent Managers always see every dashboard, in full. Anyone else needs one of these roles and access to Leads; the scope then keeps them to their part.'
            )
          "
        >
          <div class="flex flex-col gap-1.5">
            <FormLabel :label="__('Roles')" size="md" />
            <ChipListInput
              v-model="form.roles"
              doctype="Role"
              :filters="{ disabled: 0, desk_access: 1 }"
              :placeholder="__('Add a role')"
            />
          </div>
          <FormControl
            v-model="form.scope"
            type="select"
            class="w-full sm:w-72"
            :label="__('Each viewer sees')"
            :options="optionsOf(registry.scopes)"
            :description="scopeHelp"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('What it covers')"
          :description="
            __(
              'Pick companies, branches, departments, teams or employees to keep the dashboard to them. Leave it empty to cover them all, new ones included.'
            )
          "
        >
          <div class="flex flex-col gap-1.5">
            <FormLabel :label="__('Only these units')" size="md" />
            <MultiSelect
              v-model="form.units"
              :options="unitOptions"
              :loading="units.loading"
              :placeholder="__('Every unit')"
              class="w-full"
            />
          </div>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.default_period"
              type="select"
              :label="__('Opens on')"
              :options="optionsOf(registry.periods)"
            />
            <FormControl
              v-model="form.value_format"
              type="select"
              :label="__('Money shown as')"
              :options="VALUE_FORMATS"
            />
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Filters')"
          :description="
            __(
              'The choices above the figures, in this order. A company narrows the branches, a branch its departments and teams, a team its employees.'
            )
          "
        >
          <ul class="flex flex-col gap-2" :aria-label="__('Filters')">
            <li
              v-for="(row, i) in form.filters"
              :key="row.filter"
              class="flex flex-wrap items-end gap-2 rounded-lg border border-outline-gray-2 px-3 py-2"
            >
              <span
                class="min-w-[8rem] flex-1 pb-1.5 text-base-medium text-ink-gray-8"
              >
                {{ registry.dimensions[row.filter] }}
              </span>
              <FormControl
                v-model="row.default_value"
                class="w-full sm:w-56"
                :label="__('Picked when it opens')"
                :placeholder="__('All')"
              />
              <RowControls
                :label="registry.dimensions[row.filter]"
                :first="i === 0"
                :last="i === form.filters.length - 1"
                @move="(d) => move(form.filters, i, d)"
                @remove="form.filters.splice(i, 1)"
              />
            </li>
          </ul>
          <FormControl
            v-if="filterChoices.length"
            :model-value="''"
            type="select"
            class="w-full sm:w-56"
            :label="__('Add a filter')"
            :options="[{ label: __('Pick one'), value: '' }, ...filterChoices]"
            @update:model-value="
              (f) => f && form.filters.push({ filter: f, default_value: '' })
            "
          />
        </SettingsSection>

        <SettingsSection
          :title="__('KPI cards')"
          :description="
            __(
              'In this order. Each can keep its own period and say what it is calculated from.'
            )
          "
        >
          <ul class="flex flex-col gap-2" :aria-label="__('KPI cards')">
            <li
              v-for="(row, i) in form.kpis"
              :key="i"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 px-3 py-3"
              :class="row.enabled ? '' : 'bg-surface-gray-1'"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="min-w-0 flex-1 text-base-medium"
                  :class="row.enabled ? 'text-ink-gray-8' : 'text-ink-gray-5'"
                >
                  {{ row.label || metricLabel(row.metric) }}
                </span>
                <Switch v-model="row.enabled" size="sm" :label="__('Show')" />
                <RowControls
                  :label="metricLabel(row.metric)"
                  :first="i === 0"
                  :last="i === form.kpis.length - 1"
                  @move="(d) => move(form.kpis, i, d)"
                  @remove="form.kpis.splice(i, 1)"
                />
              </div>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-4">
                <FormControl
                  v-model="row.label"
                  :label="__('Label')"
                  :placeholder="metricLabel(row.metric)"
                />
                <FormControl
                  v-model="row.period"
                  type="select"
                  :label="__('Period')"
                  :options="periodOptions"
                />
                <FormControl
                  v-if="basisOptions(row.metric).length"
                  v-model="row.basis"
                  type="select"
                  :label="__('Calculated from')"
                  :options="basisOptions(row.metric)"
                />
                <FormControl
                  v-if="aggregationOptions(row.metric).length"
                  v-model="row.aggregation"
                  type="select"
                  :label="__('Shown as')"
                  :options="aggregationOptions(row.metric)"
                />
              </div>
            </li>
          </ul>
          <FormControl
            :model-value="''"
            type="select"
            class="w-full sm:w-64"
            :label="__('Add a card')"
            :options="[
              { label: __('Pick a metric'), value: '' },
              ...metricOptions,
            ]"
            @update:model-value="addKpi"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Charts and reports')"
          :description="
            __('In this order; a full-width one takes a whole row.')
          "
        >
          <ul
            class="flex flex-col gap-2"
            :aria-label="__('Charts and reports')"
          >
            <li
              v-for="(row, i) in form.charts"
              :key="i"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 px-3 py-3"
              :class="row.enabled ? '' : 'bg-surface-gray-1'"
            >
              <div class="flex flex-wrap items-end gap-2">
                <FormControl
                  v-model="row.title"
                  class="min-w-[12rem] flex-1"
                  :label="__('Title')"
                  maxlength="140"
                />
                <Switch v-model="row.enabled" size="sm" :label="__('Show')" />
                <RowControls
                  :label="row.title"
                  :first="i === 0"
                  :last="i === form.charts.length - 1"
                  @move="(d) => move(form.charts, i, d)"
                  @remove="form.charts.splice(i, 1)"
                />
              </div>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-4">
                <FormControl
                  v-model="row.chart_type"
                  type="select"
                  :label="__('Chart')"
                  :options="optionsOf(registry.chart_types)"
                  @update:model-value="
                    (t) => t === 'line' && (row.dimension = 'month')
                  "
                />
                <FormControl
                  v-model="row.dimension"
                  type="select"
                  :label="__('Group by')"
                  :disabled="row.chart_type === 'line'"
                  :options="optionsOf(registry.dimensions)"
                />
                <FormControl
                  v-model="row.metric"
                  type="select"
                  :label="
                    row.chart_type === 'table' ? __('Sorted by') : __('Metric')
                  "
                  :options="chartMetricOptions(row)"
                  @update:model-value="() => resetCalculation(row)"
                />
                <FormControl
                  v-if="row.chart_type === 'bar' || row.chart_type === 'line'"
                  v-model="row.compare_metric"
                  type="select"
                  :label="__('Compare with')"
                  :options="compareOptions(row)"
                />
                <FormControl
                  v-if="basisOptions(row.metric).length"
                  v-model="row.basis"
                  type="select"
                  :label="__('Calculated from')"
                  :options="basisOptions(row.metric)"
                />
                <FormControl
                  v-if="aggregationOptions(row.metric).length"
                  v-model="row.aggregation"
                  type="select"
                  :label="__('Shown as')"
                  :options="aggregationOptions(row.metric)"
                />
                <FormControl
                  v-model="row.period"
                  type="select"
                  :label="__('Period')"
                  :options="periodOptions"
                />
                <FormControl
                  v-if="row.dimension !== 'month'"
                  v-model="row.sort"
                  type="select"
                  :label="__('Sort')"
                  :options="optionsOf(registry.sorts)"
                />
                <FormControl
                  v-model="row.max_items"
                  type="number"
                  min="1"
                  max="50"
                  :label="
                    row.dimension === 'month'
                      ? __('Months shown')
                      : __('Show at most')
                  "
                />
                <FormControl
                  v-model="row.width"
                  type="select"
                  :label="__('Width')"
                  :options="WIDTHS"
                />
              </div>
            </li>
          </ul>
          <div>
            <Dropdown :options="chartMenu">
              <Button :label="__('Add a chart')">
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </Dropdown>
          </div>
        </SettingsSection>

        <ConfigHistory
          doctype="HD CRM Dashboard"
          :name="name"
          :version="config.data.modified"
        />
      </div>
    </template>
  </SettingsLayoutBase>
  <ConfirmDialog
    v-model="confirmLeave"
    :title="__('Leave without saving?')"
    :message="
      __('Your changes on this page haven\'t been saved and will be lost.')
    "
    :on-confirm="() => emit('back')"
    :on-cancel="() => (confirmLeave = false)"
  />
</template>

<script setup lang="ts">
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { showSettingsModal } from "@/components/Settings/settingsModal";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  Dropdown,
  FormControl,
  FormLabel,
  MultiSelect,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import LucideExternalLink from "~icons/lucide/external-link";
import LucidePlus from "~icons/lucide/plus";
import ChipListInput from "../ChipListInput.vue";
import SettingsSection from "../SettingsSection.vue";
import ConfigHistory from "./ConfigHistory.vue";
import RowControls from "./RowControls.vue";
import {
  optionsOf,
  unitTypeLabel,
  type ChartRow,
  type OrgUnit,
  type Registry,
} from "./crmDashboards";

interface KpiRow {
  metric: string;
  enabled: boolean;
  label: string;
  period: string;
  basis: string;
  aggregation: string;
}

interface EditableChart extends Omit<ChartRow, "enabled"> {
  enabled: boolean;
  basis?: string;
  aggregation?: string;
}

const props = defineProps<{ name: string; registry: Registry }>();
const emit = defineEmits<{ back: [] }>();

const API = "helpdesk.api.crm_dashboard_settings";
const FOLLOW = "dashboard";
const VALUE_FORMATS = [
  { label: __("Short (₹12.4L)"), value: "short" },
  { label: __("Full (₹12,40,000)"), value: "full" },
];
const WIDTHS = [
  { label: __("Half"), value: "half" },
  { label: __("Full width"), value: "full" },
];

const router = useRouter();

const form = reactive({
  dashboard_name: "",
  description: "",
  is_active: false,
  is_default: false,
  scope: "all",
  default_period: "this_month",
  value_format: "short",
  roles: [] as string[],
  units: [] as string[],
  filters: [] as { filter: string; default_value: string }[],
  kpis: [] as KpiRow[],
  charts: [] as EditableChart[],
});
const saved = ref("");

const config = createResource({
  url: `${API}.get_dashboard_config`,
  makeParams: () => ({ name: props.name }),
  auto: true,
  onSuccess: fill,
});

function fill(data: any) {
  Object.assign(form, {
    dashboard_name: data.dashboard_name || "",
    description: data.description || "",
    is_active: !!data.is_active,
    is_default: !!data.is_default,
    scope: data.scope,
    default_period: data.default_period,
    value_format: data.value_format || "short",
    roles: data.roles.map((r: { role: string }) => r.role),
    units: data.units.map((u: { unit: string }) => u.unit),
    filters: data.filters.map((f: any) => ({
      filter: f.filter,
      default_value: f.default_value || "",
    })),
    kpis: data.kpis.map((k: any) => ({
      metric: k.metric,
      enabled: !!k.enabled,
      label: k.label || "",
      period: k.period || FOLLOW,
      basis: k.basis || "",
      aggregation: k.aggregation || "",
    })),
    charts: data.charts.map((c: any) => ({ ...c, enabled: !!c.enabled })),
  });
  saved.value = JSON.stringify(form);
}

const dirty = computed(
  () => !!saved.value && JSON.stringify(form) !== saved.value
);

const units = createResource<OrgUnit[]>({
  url: `${API}.get_units`,
  auto: true,
});
const unitOptions = computed(() =>
  (units.data || []).map((u) => ({
    label: `${unitTypeLabel(u.unit_type)}: ${u.label} · ${u.source}`,
    value: u.name,
  }))
);

const scopeHelp = computed(
  () =>
    ({
      all: __("Everything the dashboard covers."),
      company: __("The companies of their employee record."),
      branch: __("The branches of their employee record."),
      department: __("The departments of their employee record."),
      team: __("The teams they lead or are in."),
      own: __("The leads they own."),
    }[form.scope] || "")
);

const periodOptions = computed(() => [
  { label: __("The dashboard's period"), value: FOLLOW },
  ...optionsOf(props.registry.periods),
]);

const metricOptions = computed(() =>
  Object.entries(props.registry.metrics).map(([value, m]) => ({
    label: m.label,
    value,
  }))
);

function metricLabel(metric: string) {
  return props.registry.metrics[metric]?.label || metric;
}

function basisOptions(metric: string) {
  const bases = props.registry.metrics[metric]?.bases || {};
  return Object.entries(bases).map(([value, b]) => ({ label: b.label, value }));
}

function aggregationOptions(metric: string) {
  return (props.registry.metrics[metric]?.aggregations || []).map((value) => ({
    label: props.registry.aggregations[value],
    value,
  }));
}

// a donut adds its slices up; a rate or an average can't be
function chartMetricOptions(row: EditableChart) {
  if (row.chart_type !== "donut") return metricOptions.value;
  return metricOptions.value.filter((o) =>
    ["count", "money"].includes(props.registry.metrics[o.value].kind)
  );
}

// two series share an axis, so they must be measured alike
function compareOptions(row: EditableChart) {
  const kind = props.registry.metrics[row.metric]?.kind;
  return [
    { label: __("Nothing"), value: "" },
    ...metricOptions.value.filter(
      (o) =>
        o.value !== row.metric && props.registry.metrics[o.value].kind === kind
    ),
  ];
}

function resetCalculation(row: EditableChart) {
  row.basis = "";
  row.aggregation = "";
  if (
    row.compare_metric &&
    compareOptions(row).every((o) => o.value !== row.compare_metric)
  )
    row.compare_metric = "";
}

const filterChoices = computed(() =>
  props.registry.filters
    .filter((f) => !form.filters.some((row) => row.filter === f))
    .map((f) => ({ label: props.registry.dimensions[f], value: f }))
);

function addKpi(metric: string) {
  if (!metric) return;
  form.kpis.push({
    metric,
    enabled: true,
    label: "",
    period: FOLLOW,
    basis: "",
    aggregation: "",
  });
}

function addChart(preset: Partial<ChartRow> & { title: string }) {
  form.charts.push({
    chart_type: "bar",
    dimension: "company",
    metric: "total_leads",
    compare_metric: "",
    period: FOLLOW,
    sort: "value_desc",
    max_items: 10,
    width: "half",
    ...preset,
    enabled: true,
  });
}

const chartMenu = computed(() => [
  ...Object.values(props.registry.chart_presets).map((preset) => ({
    label: preset.title,
    onClick: () => addChart(preset),
  })),
  {
    label: __("Blank chart"),
    onClick: () => addChart({ title: __("New chart") }),
  },
]);

function move<T>(list: T[], index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= list.length) return;
  const [row] = list.splice(index, 1);
  list.splice(target, 0, row);
}

const saving = ref(false);
async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    const result = await call(`${API}.save_dashboard`, {
      name: props.name,
      values: {
        dashboard_name: form.dashboard_name,
        description: form.description,
        is_active: form.is_active ? 1 : 0,
        is_default: form.is_default ? 1 : 0,
        scope: form.scope,
        default_period: form.default_period,
        value_format: form.value_format,
        roles: form.roles.map((role) => ({ role })),
        units: form.units.map((unit) => ({ unit })),
        filters: form.filters,
        kpis: form.kpis.map((k) => ({ ...k, enabled: k.enabled ? 1 : 0 })),
        charts: form.charts.map((c) => ({ ...c, enabled: c.enabled ? 1 : 0 })),
      },
    });
    config.setData(result);
    fill(result);
    toast.success(__("Dashboard saved"));
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save the dashboard. Try again.")));
  } finally {
    saving.value = false;
  }
}

const confirmLeave = ref(false);
function back() {
  if (dirty.value) confirmLeave.value = true;
  else emit("back");
}

function preview() {
  showSettingsModal.value = false;
  router.push({ name: "CrmDashboard", params: { dashboardId: props.name } });
}
</script>
