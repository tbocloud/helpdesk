<template>
  <SettingsSection
    :title="__('ERP sites')"
    :description="
      __(
        'Each division\'s ERPNext site: how its leads are read, which of their fields mean what, how its statuses count and whose roles there count.'
      )
    "
  >
    <template #actions>
      <Button :label="__('Add ERP site')" @click="emit('open', null)">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <div class="flex flex-col gap-4">
      <SettingsList
        :items="sites.data?.sources"
        :label="__('ERP sites')"
        :loading="sites.loading && !sites.data"
        :empty-icon="LucideDatabase"
        :empty-title="__('No ERP sites yet')"
        :empty-message="
          __(
            'Add one for each division\'s ERPNext site, then pick it on the division.'
          )
        "
        row-key="name"
      >
        <template #default="{ item }">
          <SettingsListItem
            :title="item.name"
            :subtitle="subtitle(item)"
            :muted="!item.enabled"
            @open="emit('open', item.name)"
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
      <p v-if="sites.error" role="alert" class="text-p-sm text-danger">
        {{ errorText(sites.error, __("Couldn't load the ERP sites.")) }}
      </p>
      <SettingRow
        :label="__('Reporting currency')"
        :description="
          __(
            'The division overview shows money in this currency; each ERP site converts its own amounts with its rate.'
          )
        "
        v-slot="{ id, labelledby }"
      >
        <Link
          :id="id"
          :labelledby="labelledby"
          :model-value="sites.data?.currency || ''"
          class="w-full sm:w-48"
          doctype="Currency"
          :placeholder="__('Pick a currency')"
          @update:model-value="setCurrency"
        />
      </SettingRow>
    </div>
  </SettingsSection>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, createResource, dayjs, toast } from "frappe-ui";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideDatabase from "~icons/lucide/database";
import LucidePlus from "~icons/lucide/plus";
import SettingRow from "../SettingRow.vue";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSection from "../SettingsSection.vue";
import {
  ERP_SITES_API,
  ERP_SITES_CACHE,
  syncSummary,
  type ErpSitesData,
} from "./erpSites";

const emit = defineEmits<{ open: [name: string | null] }>();

const sites = createResource<ErpSitesData>({
  url: `${ERP_SITES_API}.get_sources`,
  cache: ERP_SITES_CACHE,
  auto: true,
});

function subtitle(item: ErpSitesData["sources"][number]) {
  return [
    item.divisions.length
      ? __("For {0}", item.divisions.join(", "))
      : __("No division uses it"),
    syncSummary(item, (d) => dayjs(d).fromNow()),
  ].join(" · ");
}

async function setCurrency(currency: string) {
  if (!currency || currency === sites.data?.currency) return;
  try {
    await call(`${ERP_SITES_API}.set_currency`, { currency });
    toast.success(__("Reporting currency saved"));
    sites.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save the currency. Try again.")));
  }
}
</script>
