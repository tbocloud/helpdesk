<template>
  <SettingsLayoutBase
    :title="__('TBO Chat')"
    :description="
      __(
        'Agents open TBO Chat from TBO Support and are signed in with their Microsoft account. People who are disabled here, or leave Microsoft, are removed from TBO Chat.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template v-if="form" #header-actions>
      <Switch v-model="form.sso_enabled" :label="__('Enabled')" />
    </template>
    <template #content>
      <div v-if="form">
        <SettingsSection
          :title="__('Connection')"
          :description="__('The same Chatwoot account the chat bridge uses.')"
        >
          <div class="flex flex-col gap-4 sm:flex-row">
            <FormControl
              v-model="form.base_url"
              class="w-full sm:w-80"
              :label="__('Chatwoot URL')"
              placeholder="https://chat.teambackoffice.com"
            />
            <FormControl
              v-model="form.account_id"
              type="number"
              class="w-full sm:w-32"
              :label="__('Account ID')"
            />
          </div>
          <SecretField
            v-model="edits.api_access_token"
            :label="LABELS.api_access_token"
            :description="
              __(
                'Access token of a Chatwoot administrator (Profile settings). Finds people in the account by email.'
              )
            "
            :status="secrets.api_access_token"
            :error="fieldErrors.api_access_token"
            type="password"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Sign-in')"
          :description="
            __(
              'Only active agents can open TBO Chat. Each sign-in uses a link that works once, for five minutes.'
            )
          "
        >
          <SecretField
            v-model="edits.platform_api_token"
            :label="LABELS.platform_api_token"
            :description="
              __(
                'From a Platform App in the Chatwoot Super Admin console (Platform Apps). Signs agents in, adds new agents and removes people who leave.'
              )
            "
            :status="secrets.platform_api_token"
            :error="fieldErrors.platform_api_token"
            type="password"
            removable
          />
          <SettingRow
            v-slot="{ id }"
            :label="__('Add agents who aren\'t in TBO Chat yet')"
            :description="
              __(
                'Off: only people already in the Chatwoot account can open TBO Chat.'
              )
            "
          >
            <Switch :id="id" v-model="form.sso_create_users" />
          </SettingRow>
          <template v-if="form.sso_create_users">
            <SettingRow v-slot="{ id }" :label="__('Role for new agents')">
              <FormControl
                :id="id"
                v-model="form.sso_default_role"
                type="select"
                class="w-full sm:w-48"
                :options="ROLES"
              />
            </SettingRow>
            <SettingRow
              v-slot="{ id }"
              :label="__('Managers join as administrators')"
              :description="
                __(
                  'New System Managers and Agent Managers. People already in TBO Chat keep their role.'
                )
              "
            >
              <Switch :id="id" v-model="form.sso_managers_as_admins" />
            </SettingRow>
          </template>
        </SettingsSection>

        <SettingsSection
          :title="__('Chatwoot\'s sign-in page')"
          :description="
            __(
              'The server sends Chatwoot\'s own sign-in page to this address, so there is no password sign-in. Agents also find Open TBO Chat in their profile menu.'
            )
          "
        >
          <code
            class="break-all rounded border border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5 font-mono text-sm text-ink-gray-8"
            >{{ data?.login_url }}</code
          >
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, reactive, ref } from "vue";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "../SecretField.vue";
import { secretValue } from "../secretEdit";

const ROLES = [
  { label: __("Agent"), value: "agent" },
  { label: __("Administrator"), value: "administrator" },
];
const SECRETS = ["api_access_token", "platform_api_token"] as const;
type Secret = typeof SECRETS[number];

// Check fields come as 0/1 and go back the same way
const CHECKS = ["sso_enabled", "sso_create_users", "sso_managers_as_admins"];

// the doctype's labels: a save error starts with one, e.g. "Platform App Token: …"
const LABELS: Record<Secret, string> = {
  api_access_token: __("Bridge User Access Token"),
  platform_api_token: __("Platform App Token"),
};

interface SettingsData {
  settings: Record<string, any>;
  secrets: Record<Secret, SecretStatus>;
  login_url: string;
}

const form = ref<Record<string, any> | null>(null);
const initial = ref("");
const edits = reactive({} as Record<Secret, SecretEdit>);
const fieldErrors = reactive({} as Partial<Record<Secret, string>>);

function load(saved: SettingsData) {
  const f = { ...saved.settings };
  for (const key of CHECKS) f[key] = Boolean(f[key]);
  form.value = f;
  initial.value = JSON.stringify(f);
  for (const key of SECRETS) {
    edits[key] = { mode: "keep", value: "" };
    delete fieldErrors[key];
  }
}

const settings = createResource({
  url: "helpdesk.api.chatwoot_sso.get_settings",
  auto: true,
  onSuccess: load,
});

const data = computed(() => settings.data as SettingsData | undefined);
const secrets = computed(
  () => data.value?.secrets ?? ({} as Record<Secret, SecretStatus>)
);

function secretParam(key: Secret): string | undefined {
  return secretValue(edits[key]);
}

const isDirty = computed(
  () =>
    !!form.value &&
    (JSON.stringify(form.value) !== initial.value ||
      SECRETS.some((key) => secretParam(key) !== undefined))
);

const save = createResource({
  url: "helpdesk.api.chatwoot_sso.save_settings",
  makeParams() {
    const values: Record<string, any> = { ...form.value };
    for (const key of CHECKS) values[key] = values[key] ? 1 : 0;
    for (const key of SECRETS) {
      const value = secretParam(key);
      if (value !== undefined) values[key] = value;
    }
    return { values };
  },
  onSuccess(saved: SettingsData) {
    settings.setData(saved);
    load(saved);
    toast.success(__("TBO Chat settings saved"));
  },
  onError(e: { messages?: string[] }) {
    const message =
      e.messages?.[0] || __("Couldn't save the TBO Chat settings");
    for (const key of SECRETS)
      fieldErrors[key] = message.startsWith(`${LABELS[key]}:`)
        ? message
        : undefined;
    toast.error(message);
  },
});
</script>
