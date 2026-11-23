<template>
  <SettingsLayoutBase
    :title="__('Audit log')"
    :description="
      __(
        'Who changed a division, its people or its ERP site, moved a project between divisions, switched division or exported a report.'
      )
    "
    :error="log.error"
    @retry="log.reload()"
  >
    <template #content>
      <SettingsList
        :items="log.data"
        :label="__('Audit log')"
        :loading="log.loading"
        :empty-icon="LucideScrollText"
        :empty-title="__('Nothing logged yet')"
        :empty-message="__('Changes to divisions show up here.')"
      >
        <template #default="{ item }">
          <div class="flex flex-col gap-1 px-3 py-3">
            <p class="text-p-xs text-ink-gray-6">
              <span class="font-medium text-ink-gray-8">{{ item.by }}</span>
              · {{ dayjs(item.at).format("D MMM YYYY, HH:mm") }}
              <template v-if="item.division"> · {{ item.division }}</template>
            </p>
            <p
              v-for="(line, i) in item.lines"
              :key="i"
              class="text-p-sm text-ink-gray-8"
            >
              {{ line }}
            </p>
          </div>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { DIVISIONS_API } from "@/pages/divisions/divisions";
import { __ } from "@/translation";
import { createResource, dayjs } from "frappe-ui";
import LucideScrollText from "~icons/lucide/scroll-text";
import SettingsList from "../SettingsList.vue";

const log = createResource<
  { at: string; by: string; division: string | null; lines: string[] }[]
>({
  url: `${DIVISIONS_API}.get_audit_log`,
  auto: true,
});
</script>
