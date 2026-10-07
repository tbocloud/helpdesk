<template>
  <SettingsSection :title="__('Workflow and knowledge base')">
    <SettingRow
      v-slot="{ id }"
      :label="__('Prefer knowledge base')"
      :description="__('Guide users to articles before tickets.')"
    >
      <Switch
        :id="id"
        :model-value="settingsData.preferKnowledgeBase"
        @update:model-value="
          (value) => (settingsData.preferKnowledgeBase = value)
        "
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Skip email workflow')"
      :description="
        __(
          'Disables all email notifications for the ticket - including creation, updates, and alerts.'
        )
      "
    >
      <Switch
        :id="id"
        :model-value="settingsData.skipEmailWorkflow"
        @update:model-value="
          (value) => (settingsData.skipEmailWorkflow = value)
        "
      />
    </SettingRow>
  </SettingsSection>
</template>

<script setup lang="ts">
import { HDSettingsSymbol } from "@/types";
import { Switch } from "frappe-ui";
import { inject } from "vue";
import SettingRow from "../../SettingRow.vue";
import SettingsSection from "../../SettingsSection.vue";

const settingsData = inject(HDSettingsSymbol);
</script>
