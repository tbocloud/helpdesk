<template>
  <SettingsLayoutBase
    :title="__('Organisation')"
    :description="
      __(
        'Where each unit sits. A lead without a team takes its employee\'s, a team its department\'s, and so up to the company. An inactive unit\'s leads count on no dashboard.'
      )
    "
    :back-label="__('Back to CRM dashboards')"
    @back="emit('back')"
  >
    <template #header-actions>
      <Button variant="solid" :label="addLabel" @click="edit(null)">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #header-bottom>
      <div class="flex flex-wrap items-center gap-2">
        <FormControl
          v-if="sources.length > 1"
          v-model="source"
          type="select"
          class="w-full sm:w-48"
          :aria-label="__('Data source')"
          :options="sources.map((s) => ({ label: s.name, value: s.name }))"
        />
        <div class="max-w-full overflow-x-auto">
          <TabButtons
            v-model="unitType"
            :aria-label="__('Kind of unit')"
            :options="
              LEVELS.map(([, type]) => ({
                label: unitTypeLabel(type, true),
                value: type,
              }))
            "
          />
        </div>
        <SettingsSearch
          v-model="search"
          class="w-full sm:w-56"
          :placeholder="__('Search units')"
        />
      </div>
    </template>
    <template #content>
      <SettingsList
        :items="shown"
        :label="unitTypeLabel(unitType, true)"
        :loading="units.loading && !units.data"
        :error="units.error"
        :filtered="!!search"
        :empty-icon="LucideNetwork"
        :empty-title="
          __('No {0} yet', [unitTypeLabel(unitType, true).toLowerCase()])
        "
        :empty-message="emptyMessage"
        @retry="units.reload()"
        @clear-filters="search = ''"
      >
        <template #default="{ item }">
          <SettingsListItem
            :title="item.label"
            :subtitle="subtitle(item)"
            :muted="!item.is_active"
            @open="edit(item)"
          >
            <template #badges>
              <TaskyBadge v-if="!item.is_active" :label="__('Inactive')" />
            </template>
            <template #meta>
              <span
                class="whitespace-nowrap text-p-sm tabular-nums text-ink-gray-6"
              >
                {{ __("{0} leads", [item.leads]) }}
              </span>
            </template>
            <template #actions>
              <Switch
                :model-value="!!item.is_active"
                :aria-label="__('Count {0}\'s leads', [item.label])"
                @update:model-value="setActive(item, $event)"
              />
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>

  <OrgUnitDialog
    v-model:open="dialogOpen"
    :unit="editing"
    :unit-type="unitType"
    :source="source"
    :units="units.data || []"
    :unit-parents="registry.unit_parents"
    @saved="units.reload()"
  />
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  FormControl,
  Switch,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideNetwork from "~icons/lucide/network";
import LucidePlus from "~icons/lucide/plus";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSearch from "../SettingsSearch.vue";
import OrgUnitDialog from "./OrgUnitDialog.vue";
import {
  LEVELS,
  unitTypeLabel,
  type OrgUnit,
  type Registry,
  type SourceSummary,
} from "./crmDashboards";

const props = defineProps<{ sources: SourceSummary[]; registry: Registry }>();
const emit = defineEmits<{ back: [] }>();

const source = ref(props.sources[0]?.name || "");
const unitType = ref<string>("Team");
const search = ref("");

const units = createResource<OrgUnit[]>({
  url: "helpdesk.api.crm_dashboard_settings.get_units",
  makeParams: () => ({ source: source.value }),
  auto: !!source.value,
});
watch(source, () => units.reload());

const shown = computed(() => {
  const q = search.value.trim().toLowerCase();
  return (units.data || []).filter(
    (u) =>
      u.unit_type === unitType.value &&
      (!q || `${u.label} ${u.unit_name}`.toLowerCase().includes(q))
  );
});

const addLabel = computed(() =>
  __("Add {0}", [unitTypeLabel(unitType.value).toLowerCase()])
);

const emptyMessage = computed(() =>
  unitType.value === "Team"
    ? __(
        "Leads rarely carry a team. Add your teams here and put employees in them."
      )
    : __(
        "They appear after a sync when the leads or ERPNext name them, or add one here."
      )
);

/** "Sales North · in North, Acme · led by Ann · on the leads as SN-01" */
function subtitle(unit: OrgUnit) {
  const parents = props.registry.unit_parents[unit.unit_type] || [];
  const above = [...parents]
    .reverse()
    .map((level) => unit[level as keyof OrgUnit])
    .filter(Boolean)
    .join(", ");
  const parts = [];
  if (above) parts.push(__("in {0}", [above]));
  if (unit.leader) parts.push(__("led by {0}", [unit.leader]));
  if (unit.user && unit.user !== unit.unit_name)
    parts.push(__("user {0}", [unit.user]));
  if (unit.label !== unit.unit_name)
    parts.push(__("on the leads as {0}", [unit.unit_name]));
  return parts.join(" · ") || __("Not placed under anything yet");
}

async function setActive(unit: OrgUnit, active: boolean) {
  try {
    await call("helpdesk.api.crm_dashboard_settings.set_unit_active", {
      name: unit.name,
      active,
    });
    unit.is_active = active ? 1 : 0;
    toast.success(
      active
        ? __("{0}'s leads are counted again", [unit.label])
        : __("{0}'s leads are left out", [unit.label])
    );
  } catch (e) {
    toast.error(errorText(e, __("Couldn't change it. Try again.")));
  }
}

const dialogOpen = ref(false);
const editing = ref<OrgUnit | null>(null);
function edit(unit: OrgUnit | null) {
  editing.value = unit;
  dialogOpen.value = true;
}
</script>
