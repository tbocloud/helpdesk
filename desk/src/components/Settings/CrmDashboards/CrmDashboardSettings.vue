<template>
  <SourceEditor
    v-if="view.kind === 'source' && settings.data"
    :name="view.name"
    :registry="settings.data.registry"
    :reporting-currency="settings.data.currency"
    :crm-connection="settings.data.crm_connection"
    @back="back"
    @saved="(name) => (view = { kind: 'source', name })"
  />
  <DashboardEditor
    v-else-if="view.kind === 'dashboard' && settings.data"
    :name="view.name"
    :registry="settings.data.registry"
    @back="back"
  />
  <OrgUnits
    v-else-if="view.kind === 'organisation' && settings.data"
    :sources="settings.data.sources"
    :registry="settings.data.registry"
    @back="back"
  />
  <SettingsLayoutBase
    v-else
    :title="__('CRM dashboards')"
    :description="
      __(
        'Lead reporting across your companies: where the leads come from, how they map, the organisation and the dashboards people see.'
      )
    "
    :dirty="currencyDirty"
    :saving="savingCurrency"
    :loading="settings.loading && !settings.data"
    :error="settings.error"
    @retry="settings.reload()"
    @save="saveCurrency"
  >
    <template #content>
      <div v-if="settings.data" class="flex flex-col">
        <SettingsSection
          :title="__('Dashboards')"
          :description="
            __(
              'Each has its own viewers, scope, filters, KPI cards and charts. A new one starts inactive, so only admins see it until you switch it on.'
            )
          "
        >
          <template #actions>
            <Button :label="__('New dashboard')" @click="newOpen = true">
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
          <SettingsList
            :items="settings.data.dashboards"
            :label="__('Dashboards')"
            :empty-icon="LucideLayoutDashboard"
            :empty-title="__('No dashboards yet')"
            :empty-message="
              __(
                'Start one from a template: executive, company, branch, department or sales team leader.'
              )
            "
          >
            <template #default="{ item }">
              <SettingsListItem
                :title="item.dashboard_name"
                :subtitle="dashboardSubtitle(item)"
                :muted="!item.is_active"
                @open="view = { kind: 'dashboard', name: item.name }"
              >
                <template #badges>
                  <TaskyBadge
                    v-if="item.is_default"
                    tone="brand"
                    :label="__('Default')"
                  />
                  <TaskyBadge v-if="!item.is_active" :label="__('Inactive')" />
                </template>
                <template #actions>
                  <Switch
                    :model-value="!!item.is_active"
                    :aria-label="
                      __('Show {0} to its viewers', [item.dashboard_name])
                    "
                    @update:model-value="setActive(item, $event)"
                  />
                  <Dropdown :options="dashboardMenu(item)" placement="right">
                    <Button
                      variant="ghost"
                      :aria-label="
                        __('More actions for {0}', [item.dashboard_name])
                      "
                    >
                      <template #icon>
                        <LucideEllipsis class="size-4" aria-hidden="true" />
                      </template>
                    </Button>
                  </Dropdown>
                </template>
              </SettingsListItem>
            </template>
          </SettingsList>
        </SettingsSection>

        <SettingsSection
          :title="__('Data sources')"
          :description="
            __(
              'Each company\'s CRM site: how its leads are read, which of their fields mean what, and how its statuses count.'
            )
          "
        >
          <template #actions>
            <Button
              :label="__('Add source')"
              @click="view = { kind: 'source', name: null }"
            >
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
          <SettingsList
            :items="settings.data.sources"
            :label="__('Data sources')"
            :empty-icon="LucideDatabase"
            :empty-title="__('No data sources yet')"
            :empty-message="
              settings.data.crm_connection.enabled
                ? __(
                    'Add one for the CRM connection\'s site, then one for each other company\'s site.'
                  )
                : __('Add one for each company\'s ERPNext or CRM site.')
            "
          >
            <template #default="{ item }">
              <SettingsListItem
                :title="item.name"
                :subtitle="syncSummary(item, (d) => dayjs(d).fromNow())"
                :muted="!item.enabled"
                @open="view = { kind: 'source', name: item.name }"
              >
                <template #badges>
                  <TaskyBadge v-if="!item.enabled" :label="__('Off')" />
                  <TaskyBadge
                    v-else-if="item.last_sync_status === 'Failed'"
                    tone="danger"
                    :icon="LucideCircleAlert"
                    :label="__('Can\'t be read')"
                  />
                </template>
              </SettingsListItem>
            </template>
          </SettingsList>
        </SettingsSection>

        <SettingsSection
          :title="__('Organisation')"
          :description="
            __(
              'Companies, branches, departments, teams and employees, as the leads and ERPNext name them. Add teams, set leaders, put people in teams, or switch a unit off.'
            )
          "
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-p-sm tabular-nums text-ink-gray-7">
              {{
                settings.data.unit_count
                  ? __("{0} units across your data sources.", [
                      settings.data.unit_count,
                    ])
                  : __("Units appear here after a data source's first sync.")
              }}
            </p>
            <Button
              :label="__('Open organisation')"
              :disabled="!settings.data.sources.length"
              @click="view = { kind: 'organisation' }"
            />
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Reporting currency')"
          :description="
            __(
              'Every dashboard shows money in this currency. Each data source converts its own amounts with its rate.'
            )
          "
        >
          <SettingRow
            :label="__('Currency')"
            :description="__('Saved with Save changes.')"
          >
            <template #default="{ id, labelledby }">
              <Link
                :id="id"
                v-model="currency"
                class="w-full sm:w-48"
                doctype="Currency"
                :labelledby="labelledby"
                :placeholder="__('Pick a currency')"
              />
            </template>
          </SettingRow>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>

  <NewDashboardDialog
    v-if="settings.data"
    v-model:open="newOpen"
    :templates="settings.data.registry.templates"
    @created="onCreated"
  />
  <DuplicateDialog
    v-model:open="duplicating.open"
    v-model:name="duplicating.name"
    :title="__('Duplicate dashboard')"
    :label="__('Name of the copy')"
    :maxlength="140"
    :loading="duplicate.loading"
    @duplicate="
      duplicate.submit({
        name: duplicating.source,
        dashboard_name: duplicating.name,
      })
    "
  />
  <Dialog
    v-model:open="deleting.open"
    :title="__('Delete {0}?', [deleting.label])"
    size="sm"
  >
    <p class="text-p-sm text-ink-gray-7">
      {{
        __(
          "Its viewers lose it, and its filters, cards and charts go with it. The leads and the organisation stay. To hide it for now, switch it off instead."
        )
      }}
    </p>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          theme="red"
          variant="solid"
          :label="__('Delete dashboard')"
          :loading="remove.loading"
          @click="remove.submit({ name: deleting.name })"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  dayjs,
  Dialog,
  Dropdown,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideDatabase from "~icons/lucide/database";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucidePlus from "~icons/lucide/plus";
import DuplicateDialog from "../DuplicateDialog.vue";
import SettingRow from "../SettingRow.vue";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSection from "../SettingsSection.vue";
import DashboardEditor from "./DashboardEditor.vue";
import NewDashboardDialog from "./NewDashboardDialog.vue";
import OrgUnits from "./OrgUnits.vue";
import SourceEditor from "./SourceEditor.vue";
import {
  syncSummary,
  type CrmDashboardSettingsData,
  type DashboardRow,
} from "./crmDashboards";

type View =
  | { kind: "list" }
  | { kind: "source"; name: string | null }
  | { kind: "dashboard"; name: string }
  | { kind: "organisation" };

const API = "helpdesk.api.crm_dashboard_settings";

const view = ref<View>({ kind: "list" });

const settings = createResource<CrmDashboardSettingsData>({
  url: `${API}.get_settings`,
  auto: true,
});

const currency = ref("");
watch(
  () => settings.data?.currency,
  (saved) => (currency.value = saved || ""),
  { immediate: true }
);
const currencyDirty = computed(
  () => !!settings.data && currency.value !== (settings.data.currency || "")
);
const savingCurrency = ref(false);

async function saveCurrency() {
  savingCurrency.value = true;
  try {
    await call(`${API}.set_currency`, { currency: currency.value });
    toast.success(__("Reporting currency saved"));
    await settings.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save the currency. Try again.")));
  } finally {
    savingCurrency.value = false;
  }
}

function back() {
  view.value = { kind: "list" };
  settings.reload();
}

function dashboardSubtitle(item: DashboardRow) {
  const registry = settings.data!.registry;
  const parts = [__("Each viewer sees: {0}", [registry.scopes[item.scope]])];
  if (item.template && registry.templates[item.template])
    parts.push(__("from {0}", [registry.templates[item.template].label]));
  return parts.join(" · ");
}

async function setActive(item: DashboardRow, active: boolean) {
  try {
    await call(`${API}.set_dashboard_active`, { name: item.name, active });
    item.is_active = active ? 1 : 0;
    toast.success(
      active
        ? __("{0} is shown to its viewers", [item.dashboard_name])
        : __("{0} is hidden from its viewers", [item.dashboard_name])
    );
  } catch (e) {
    toast.error(errorText(e, __("Couldn't change it. Try again.")));
  }
}

function onCreated(name: string) {
  newOpen.value = false;
  view.value = { kind: "dashboard", name };
}
const newOpen = ref(false);

const duplicating = reactive({ open: false, name: "", source: "" });
const duplicate = createResource({
  url: `${API}.duplicate_dashboard`,
  onSuccess(config: { name: string }) {
    duplicating.open = false;
    toast.success(__("Copy made; it starts inactive"));
    view.value = { kind: "dashboard", name: config.name };
  },
  onError: (e: unknown) =>
    toast.error(errorText(e, __("Couldn't make the copy. Try again."))),
});

const deleting = reactive({ open: false, name: "", label: "" });
const remove = createResource({
  url: `${API}.delete_dashboard`,
  onSuccess() {
    deleting.open = false;
    toast.success(__("Dashboard deleted"));
    settings.reload();
  },
  onError: (e: unknown) =>
    toast.error(errorText(e, __("Couldn't delete it. Try again."))),
});

function dashboardMenu(item: DashboardRow) {
  return [
    {
      label: __("Duplicate"),
      onClick: () =>
        Object.assign(duplicating, {
          open: true,
          source: item.name,
          name: __("{0} (copy)", [item.dashboard_name]),
        }),
    },
    {
      label: __("Delete"),
      onClick: () =>
        Object.assign(deleting, {
          open: true,
          name: item.name,
          label: item.dashboard_name,
        }),
    },
  ];
}
</script>
