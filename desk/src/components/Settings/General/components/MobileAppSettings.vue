<template>
  <SettingsSection v-if="settingsData" :title="__('Mobile app')">
    <SettingRow
      v-slot="{ id }"
      :label="__('Mobile push')"
      :description="
        __(
          'Send each new notification to the TBO Smart app on the person\'s phones.'
        )
      "
    >
      <Switch :id="id" v-model="settingsData.enableMobilePush" />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Single sign-in with Microsoft')"
      :description="
        canEnableSso
          ? __(
              'Staff sign in to TBO Smart once with Microsoft; this site then signs in the matching agent.'
            )
          : __(
              'Fill in the tenant ID, the app client ID and the OAuth client below first.'
            )
      "
    >
      <Switch
        :id="id"
        v-model="settingsData.enableMicrosoftSso"
        :disabled="!canEnableSso && !settingsData.enableMicrosoftSso"
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Microsoft tenant ID')"
      :description="__('Directory (tenant) ID in Microsoft Entra.')"
    >
      <FormControl
        :id="id"
        v-model="settingsData.microsoftTenantId"
        type="text"
        class="w-full font-mono sm:w-80"
        placeholder="00000000-0000-0000-0000-000000000000"
        autocomplete="off"
        spellcheck="false"
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Mobile app client ID')"
      :description="
        __('Application (client) ID of the TBO Smart app registration.')
      "
    >
      <FormControl
        :id="id"
        v-model="settingsData.microsoftClientId"
        type="text"
        class="w-full font-mono sm:w-80"
        placeholder="00000000-0000-0000-0000-000000000000"
        autocomplete="off"
        spellcheck="false"
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id, labelledby }"
      :label="__('OAuth client for TBO Smart')"
      :description="__('Signed-in phones get tokens from this OAuth client.')"
    >
      <SelectDropdown
        :id="id"
        :labelledby="labelledby"
        :options="oauthClients.data || []"
        v-model="settingsData.mobileOauthClient"
        target-class="w-full sm:w-80"
        placement="bottom-start"
      />
    </SettingRow>
  </SettingsSection>
</template>

<script setup lang="ts">
import SelectDropdown from "@/components/SelectDropdown.vue";
import { __ } from "@/translation";
import { HDSettingsSymbol } from "@/types";
import { createListResource, FormControl, Switch } from "frappe-ui";
import { computed, inject } from "vue";
import SettingRow from "../../SettingRow.vue";
import SettingsSection from "../../SettingsSection.vue";

const settingsData = inject(HDSettingsSymbol);

// the server refuses to switch it on without all three (HD Settings validate)
const canEnableSso = computed(() =>
  Boolean(
    settingsData.value.microsoftTenantId?.trim() &&
      settingsData.value.microsoftClientId?.trim() &&
      settingsData.value.mobileOauthClient
  )
);

const oauthClients = createListResource({
  doctype: "OAuth Client",
  fields: ["name", "app_name"],
  orderBy: "app_name asc",
  pageLength: 100,
  auto: true,
  transform: (data: { name: string; app_name: string }[]) =>
    data.map((client) => ({
      label: client.app_name || client.name,
      value: client.name,
    })),
});
</script>
