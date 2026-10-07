<template>
  <SettingsLayoutBase
    :title="__('CRM')"
    :description="
      __(
        'Connect TBO Support to the TBO CRM site, so every agent also has a CRM user.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template #content>
      <div v-if="form">
        <SettingsSection
          :title="__('Connection')"
          :description="
            __(
              'On the CRM site, open a System Manager user → API Access → Generate Keys. Paste the keys here, never in chat or email.'
            )
          "
        >
          <FormControl
            v-model="form.site_url"
            :label="__('CRM site URL')"
            placeholder="https://tboindia.tbocloud.in"
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.api_key"
              :label="__('API key')"
              autocomplete="off"
            />
            <FormControl
              v-model="form.api_secret"
              type="password"
              :label="__('API secret')"
              :placeholder="
                hasSecret ? __('Saved. Type a new one to replace it.') : ''
              "
              autocomplete="new-password"
            />
          </div>
          <Switch v-model="form.enabled" :label="__('Enabled')" />
          <div class="flex flex-wrap items-center gap-3">
            <Button
              :label="__('Test connection')"
              :loading="test.loading"
              :disabled="isDirty"
              :tooltip="isDirty ? __('Save your changes first') : ''"
              @click="test.submit()"
            >
              <template #prefix>
                <LucidePlugZap class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <span
              v-if="test.data"
              role="status"
              class="inline-flex items-center gap-1.5 text-p-sm"
              :class="test.data.ok ? 'text-success' : 'text-danger'"
            >
              <component
                :is="test.data.ok ? LucideCircleCheck : LucideCircleAlert"
                class="size-4"
                aria-hidden="true"
              />
              {{ test.data.message }}
            </span>
          </div>
          <p v-if="isDirty" class="text-p-xs text-ink-gray-5">
            {{ __("Save your changes before testing the connection.") }}
          </p>
        </SettingsSection>

        <SettingsSection :title="__('Users')">
          <Switch
            v-model="form.sync_users"
            :label="__('Add helpdesk agents missing in the CRM')"
            :description="
              __(
                'Checked every hour and when an agent is added or leaves. Existing CRM users keep their roles.'
              )
            "
          />
          <Switch
            v-model="form.add_crm_users"
            :label="__('Add CRM users missing in helpdesk, as agents')"
            :description="__('Existing helpdesk users are left as they are.')"
          />
          <Switch
            v-model="form.disable_left_users"
            :label="__('Disable CRM users who leave helpdesk')"
            :description="
              __(
                'Only users this connection created in the CRM; people created there directly are never touched.'
              )
            "
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.crm_role"
              type="select"
              :label="__('CRM role for new users')"
              :options="ROLES"
            />
          </div>
          <Switch
            v-model="form.send_welcome_email"
            :label="__('Send new users a welcome email to set their password')"
          />
        </SettingsSection>

        <SettingsSection :title="__('Customers')">
          <Switch
            v-model="form.sync_customers"
            :label="__('Sync customers both ways')"
            :description="
              __(
                'An HD Customer missing in the CRM becomes a CRM Organization, and the other way round. Matched by name; nothing existing is changed.'
              )
            "
          />
          <div class="flex flex-wrap items-center gap-3">
            <Button
              :label="__('Sync now')"
              :loading="sync.loading"
              :disabled="isDirty"
              :tooltip="isDirty ? __('Save your changes first') : ''"
              @click="sync.submit()"
            >
              <template #prefix>
                <LucideRefreshCw class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <p
            v-if="lastResult"
            class="text-p-sm"
            :class="lastFailed ? 'text-danger' : 'text-ink-gray-6'"
          >
            {{ lastResult }}
          </p>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import {
  Button,
  createResource,
  dayjs,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucidePlugZap from "~icons/lucide/plug-zap";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import SettingsSection from "../SettingsSection.vue";

interface CRMForm {
  enabled: boolean;
  site_url: string;
  api_key: string;
  api_secret: string;
  sync_users: boolean;
  crm_role: string;
  send_welcome_email: boolean;
  add_crm_users: boolean;
  disable_left_users: boolean;
  sync_customers: boolean;
}

const DOCTYPE = "HD CRM Settings";
const ROLES = [
  { label: __("Sales User"), value: "Sales User" },
  { label: __("Sales Manager"), value: "Sales Manager" },
];

const form = ref<CRMForm | null>(null);
const initial = ref("");
const hasSecret = ref(false);
const lastSync = ref<{ on?: string; result?: string }>({});

// a new single has no saved value yet; these switches start on
function onByDefault(value: unknown) {
  return value === undefined || value === null ? true : Boolean(value);
}

const settings = createResource({
  url: "frappe.client.get",
  params: { doctype: DOCTYPE, name: DOCTYPE },
  auto: true,
  onSuccess(doc) {
    hasSecret.value = Boolean(doc.api_secret);
    lastSync.value = { on: doc.last_sync_on, result: doc.last_sync_result };
    form.value = {
      enabled: Boolean(doc.enabled),
      site_url: doc.site_url || "",
      api_key: doc.api_key || "",
      // the saved secret never comes back; only a newly typed one is sent
      api_secret: "",
      sync_users: doc.sync_users === undefined ? true : Boolean(doc.sync_users),
      crm_role: doc.crm_role || "Sales User",
      send_welcome_email:
        doc.send_welcome_email === undefined
          ? true
          : Boolean(doc.send_welcome_email),
      add_crm_users: onByDefault(doc.add_crm_users),
      disable_left_users: onByDefault(doc.disable_left_users),
      sync_customers: onByDefault(doc.sync_customers),
    };
    initial.value = JSON.stringify(form.value);
  },
});

const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);

const save = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    const f = form.value!;
    const fieldname: Record<string, unknown> = {
      ...f,
      enabled: f.enabled ? 1 : 0,
      sync_users: f.sync_users ? 1 : 0,
      send_welcome_email: f.send_welcome_email ? 1 : 0,
      add_crm_users: f.add_crm_users ? 1 : 0,
      disable_left_users: f.disable_left_users ? 1 : 0,
      sync_customers: f.sync_customers ? 1 : 0,
    };
    if (!f.api_secret) delete fieldname.api_secret;
    return { doctype: DOCTYPE, name: DOCTYPE, fieldname };
  },
  onSuccess() {
    toast.success(__("CRM settings saved"));
    settings.reload();
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save the CRM settings"));
  },
});

const test = createResource({
  url: "helpdesk.api.crm.test_connection",
  method: "POST",
});

const sync = createResource({
  url: "helpdesk.api.crm.sync_now",
  method: "POST",
  onSuccess(data: { ok: boolean; message: string }) {
    lastSync.value = { on: dayjs().format(), result: data.message };
    if (data.ok) toast.success(__("Synced with the CRM"));
    else toast.error(data.message || __("Some records couldn't be synced"));
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't sync users"));
  },
});

const lastResult = computed(() =>
  lastSync.value.result
    ? `${dayjs(lastSync.value.on).fromNow()}: ${lastSync.value.result}`
    : ""
);
const lastFailed = computed(() =>
  (lastSync.value.result || "").includes("Failed")
);
</script>
