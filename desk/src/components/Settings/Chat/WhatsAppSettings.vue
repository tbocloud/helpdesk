<template>
  <SettingsSection
    :title="__('WhatsApp outreach')"
    :description="
      __(
        'Send approved WhatsApp messages from TBO Chat, and see the replies on the lead. Leave the inbox blank to keep sending by hand with Open WhatsApp.'
      )
    "
  >
    <template v-if="form">
      <SettingRow
        v-slot="{ id }"
        :label="__('WhatsApp inbox ID')"
        :description="
          __('The number in the inbox\'s address in TBO Chat: …/inbox/9.')
        "
      >
        <FormControl
          :id="id"
          v-model="form.whatsapp_inbox_id"
          type="number"
          class="w-full sm:w-32"
        />
      </SettingRow>
      <SettingRow
        v-slot="{ id }"
        :label="__('Default country code')"
        :description="__('Added to numbers saved without one: 91 for India.')"
      >
        <FormControl
          :id="id"
          v-model="form.whatsapp_country_code"
          class="w-full sm:w-32"
        />
      </SettingRow>
      <SettingRow
        v-slot="{ id }"
        :label="__('Send WhatsApp automatically after approval')"
        :description="
          __(
            'Off: an approved message waits for the person to open WhatsApp and send it.'
          )
        "
      >
        <Switch :id="id" v-model="form.whatsapp_auto_send" />
      </SettingRow>

      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0">
            <h3 class="text-base-medium text-ink-gray-8">
              {{ __("Approved templates") }}
            </h3>
            <p class="max-w-prose text-p-sm text-ink-gray-6">
              {{
                __(
                  "WhatsApp only allows approved message templates for a first message. Create and approve them in Meta WhatsApp Manager, then read them here."
                )
              }}
            </p>
          </div>
          <div class="flex shrink-0 gap-2">
            <Button
              :label="__('Read from TBO Chat')"
              :loading="sync.loading"
              :disabled="!connected"
              @click="sync.submit()"
            >
              <template #prefix>
                <LucideRefreshCw class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button :label="__('Add by hand')" @click="addTemplate" />
          </div>
        </div>
        <p
          v-if="syncMessage"
          role="status"
          class="text-p-sm"
          :class="syncOk ? 'text-ink-gray-8' : 'text-danger'"
        >
          {{ syncMessage }}
        </p>
        <p
          v-if="!form.templates.length"
          class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-p-sm text-ink-gray-6"
        >
          {{
            __(
              "No templates yet. Without one, a first message is sent by hand."
            )
          }}
        </p>
        <ul v-else role="list" class="flex flex-col gap-3">
          <li
            v-for="(row, i) in form.templates"
            :key="i"
            class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 p-3"
          >
            <div class="flex flex-col gap-3 sm:flex-row">
              <FormControl
                v-model="row.template_name"
                class="w-full sm:flex-1"
                :label="__('Template name')"
                placeholder="tbo_intro"
              />
              <FormControl
                v-model="row.language"
                class="w-full sm:w-24"
                :label="__('Language')"
              />
            </div>
            <FormControl
              v-model="row.body"
              type="textarea"
              :rows="3"
              :label="__('Text')"
              :description="
                __('Use {{1}}, {{2}} for the blanks, as approved by Meta.')
              "
            />
            <FormControl
              v-model="row.variables"
              :label="__('Fills the blanks with')"
              :description="
                __(
                  'In order, from: name, company, why_call (the Why call line). Example: name,why_call'
                )
              "
            />
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="flex flex-wrap gap-x-5 gap-y-2">
                <Switch v-model="row.enabled" :label="__('In use')" />
                <Switch
                  :model-value="row.is_default"
                  :label="__('For first messages')"
                  @update:model-value="makeDefault(i, $event)"
                />
              </div>
              <Button
                variant="ghost"
                :label="__('Remove')"
                @click="form.templates.splice(i, 1)"
              />
            </div>
          </li>
        </ul>
      </div>

      <div class="flex justify-end">
        <Button
          variant="solid"
          :label="__('Save WhatsApp settings')"
          :loading="save.loading"
          :disabled="!isDirty"
          @click="save.submit()"
        />
      </div>
    </template>
  </SettingsSection>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";

interface Template {
  template_name: string;
  language: string;
  enabled: boolean;
  is_default: boolean;
  body: string;
  variables: string;
}
interface Form {
  whatsapp_inbox_id: number | null;
  whatsapp_country_code: string;
  whatsapp_auto_send: boolean;
  templates: Template[];
}
interface Saved {
  settings: Omit<Form, "templates">;
  templates: Template[];
  connected: boolean;
}

const form = ref<Form | null>(null);
const initial = ref("");
const connected = ref(false);
const syncMessage = ref("");
const syncOk = ref(true);

function load(saved: Saved) {
  form.value = {
    whatsapp_inbox_id: saved.settings.whatsapp_inbox_id || null,
    whatsapp_country_code: saved.settings.whatsapp_country_code || "91",
    whatsapp_auto_send: Boolean(saved.settings.whatsapp_auto_send),
    templates: saved.templates.map((row) => ({
      ...row,
      enabled: Boolean(row.enabled),
      is_default: Boolean(row.is_default),
    })),
  };
  initial.value = JSON.stringify(form.value);
  connected.value = saved.connected;
}

createResource({
  url: "helpdesk.api.whatsapp.get_settings",
  auto: true,
  onSuccess: load,
});

const isDirty = computed(() => JSON.stringify(form.value) !== initial.value);

function addTemplate() {
  form.value?.templates.push({
    template_name: "",
    language: "en",
    enabled: true,
    is_default: !form.value.templates.length,
    body: "",
    variables: "name,why_call,company",
  });
}

// one template is the first message
function makeDefault(index: number, on: boolean) {
  form.value?.templates.forEach((row, i) => {
    row.is_default = on && i === index;
  });
}

const save = createResource({
  url: "helpdesk.api.whatsapp.save_settings",
  method: "POST",
  makeParams() {
    const { templates, ...values } = form.value!;
    return {
      values: {
        ...values,
        whatsapp_inbox_id: values.whatsapp_inbox_id || 0,
        whatsapp_auto_send: values.whatsapp_auto_send ? 1 : 0,
      },
      templates: templates.map((row) => ({
        ...row,
        enabled: row.enabled ? 1 : 0,
        is_default: row.is_default ? 1 : 0,
      })),
    };
  },
  onSuccess(saved: Saved) {
    load(saved);
    toast.success(__("WhatsApp settings saved"));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save the WhatsApp settings")));
  },
});

// saving first keeps the inbox the person just typed: the server reads the saved one
const sync = createResource({
  url: "helpdesk.api.whatsapp.sync_templates",
  method: "POST",
  onSuccess(answer: Saved & { ok: boolean; message: string }) {
    syncOk.value = answer.ok;
    syncMessage.value = answer.message;
    if (answer.ok) load(answer);
  },
  onError(e: unknown) {
    syncOk.value = false;
    syncMessage.value = errorText(e, __("Couldn't read the templates"));
  },
});
</script>
