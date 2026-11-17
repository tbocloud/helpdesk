<template>
  <SettingsLayoutBase
    :title="__('Divisions')"
    :description="
      __(
        'The countries and business divisions, their workspaces, ERP sites and people. Each division sees only its own records.'
      )
    "
    :error="divisions.error"
    @retry="divisions.reload()"
  >
    <template v-if="divisions.data?.can_create" #header-actions>
      <Button
        variant="solid"
        :label="__('New division')"
        @click="emit('open', null)"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #content>
      <div class="flex flex-col gap-4">
        <p
          v-if="divisions.data?.can_create"
          class="flex items-center gap-2 text-p-sm text-ink-gray-7"
        >
          <LucideGlobe
            class="size-4 shrink-0 text-ink-gray-6"
            aria-hidden="true"
          />
          <span>
            {{ __("Central administration:") }}
            <span class="font-mono">{{ divisions.data.central_url }}</span>
          </span>
        </p>

        <!-- records made before divisions: visible to everyone until placed -->
        <div
          v-if="
            divisions.data?.unassigned_projects &&
            divisions.data.divisions.length
          "
          role="status"
          class="flex flex-wrap items-center gap-3 rounded-xl bg-warning-soft px-4 py-3 text-p-sm text-warning"
        >
          <LucideTriangleAlert class="size-4 shrink-0" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            {{
              __(
                "{0} projects have no division, so every member of every division can see them as before.",
                String(divisions.data.unassigned_projects)
              )
            }}
          </span>
          <Dropdown :options="assignOptions">
            <Button
              :label="__('Put them in a division')"
              :loading="assign.loading"
            >
              <template #suffix>
                <LucideChevronDown class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </Dropdown>
        </div>

        <SettingsList
          :items="divisions.data?.divisions"
          :label="__('Divisions')"
          :loading="divisions.loading"
          :empty-icon="LucideGlobe"
          :empty-title="__('No divisions yet')"
          :empty-message="
            __(
              'Until there is one, everyone works as before. Add India, KSA, UAE and the rest to give each its own people and records.'
            )
          "
          row-key="name"
        >
          <template #default="{ item }">
            <SettingsListItem
              :title="`${item.division_name} · ${item.name}`"
              :subtitle="subtitle(item)"
              :muted="item.status !== 'Active'"
              @open="emit('open', item.name)"
            >
              <template v-if="item.status !== 'Active'" #badges>
                <TaskyBadge :label="__('Inactive')" />
              </template>
            </SettingsListItem>
          </template>
        </SettingsList>

        <ErpSites
          v-if="divisions.data?.can_create"
          @open="emit('openSource', $event)"
        />
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { DIVISIONS_API } from "@/pages/divisions/divisions";
import { __ } from "@/translation";
import { Button, createResource, Dropdown, toast } from "frappe-ui";
import { computed } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideGlobe from "~icons/lucide/globe";
import LucidePlus from "~icons/lucide/plus";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import ErpSites from "./ErpSites.vue";

interface DivisionSummary {
  name: string;
  division_name: string;
  status: string;
  country: string;
  currency: string;
  workspace_url: string | null;
  crm_source: string | null;
  members: number;
  teams: number;
  projects: number;
}

const emit = defineEmits<{
  open: [name: string | null];
  openSource: [name: string | null];
}>();

const divisions = createResource<{
  divisions: DivisionSummary[];
  can_create: boolean;
  central_url: string;
  unassigned_projects: number;
}>({
  url: `${DIVISIONS_API}.get_divisions`,
  auto: true,
});

function subtitle(d: DivisionSummary) {
  return [
    d.country,
    d.currency,
    d.workspace_url?.replace(/^https?:\/\//, ""),
    __("{0} people", String(d.members)),
    __("{0} projects", String(d.projects)),
    d.crm_source ? __("ERP: {0}", d.crm_source) : __("No ERP site"),
  ]
    .filter(Boolean)
    .join(" · ");
}

const assign = createResource({
  url: `${DIVISIONS_API}.assign_unassigned_projects`,
  onSuccess(result: { moved: number; skipped: string[] }) {
    toast.success(
      result.skipped.length
        ? __(
            "{0} projects moved; {1} stayed because their people aren't in that division",
            String(result.moved),
            String(result.skipped.length)
          )
        : __("{0} projects moved", String(result.moved))
    );
    divisions.reload();
  },
  onError(error: any) {
    toast.error(error?.messages?.[0] || __("Couldn't move the projects"));
  },
});

const assignOptions = computed(() =>
  (divisions.data?.divisions || [])
    .filter((d) => d.status === "Active")
    .map((d) => ({
      label: d.division_name,
      onClick: () => assign.submit({ division: d.name }),
    }))
);
</script>
