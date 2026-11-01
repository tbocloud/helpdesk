<template>
  <SettingsLayoutBase
    :title="__('Meta')"
    :description="
      __(
        'Publish client-approved content posts to the client\'s Facebook Page and Instagram from the content calendar.'
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
      <Switch v-model="form.enabled" :label="__('Enabled')" />
    </template>
    <template #content>
      <div v-if="form">
        <SettingsSection
          :title="__('Meta app')"
          :description="
            __(
              'Create the app once at developers.facebook.com (type Business) and paste its App ID and secret here. Clients connect their own Page from their project.'
            )
          "
        >
          <div class="flex flex-col gap-1.5">
            <FormControl
              v-model="form.app_id"
              :label="__('App ID')"
              placeholder="1234567890"
              autocomplete="off"
            />
            <ErrorMessage
              v-if="fieldErrors.app_id"
              role="alert"
              :message="fieldErrors.app_id"
            />
          </div>
          <SecretField
            v-model="edit"
            :label="__('App Secret')"
            :description="
              __(
                'Meta app dashboard → App settings → Basic. It never comes back to the browser once saved.'
              )
            "
            :status="secret"
            :error="fieldErrors.app_secret"
            type="password"
            removable
          >
            <SettingsAction
              v-if="secret.set"
              :key="`test-${saves}`"
              method="helpdesk.api.meta.test_app"
              :label="__('Test the app')"
              :icon="LucideKeyRound"
              :unsaved="isDirty"
            />
          </SecretField>
          <div class="flex flex-col gap-1.5">
            <FormControl
              v-model="form.graph_api_version"
              :label="__('Graph API version')"
              :description="
                __(
                  'Meta retires a version about two years after its release. Change it here when upgrading; nothing else needs editing.'
                )
              "
              placeholder="v25.0"
            />
            <ErrorMessage
              v-if="fieldErrors.graph_api_version"
              role="alert"
              :message="fieldErrors.graph_api_version"
            />
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('OAuth redirect URL')"
          :description="
            __(
              'Add this under Facebook Login → Settings → Valid OAuth Redirect URIs, exactly as shown.'
            )
          "
        >
          <div class="flex flex-wrap items-center gap-2">
            <code
              :aria-label="__('OAuth redirect URL')"
              class="min-w-0 flex-1 break-all rounded border border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5 font-mono text-sm text-ink-gray-8"
            >
              {{ data?.redirect_url }}
            </code>
            <Button
              :label="__('Copy')"
              @click="
                copyToClipboard(data?.redirect_url, __('Redirect URL copied'))
              "
            >
              <template #prefix>
                <LucideCopy class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </SettingsSection>

        <SettingsSection :title="__('What the app needs from Meta')">
          <ol
            class="flex list-decimal flex-col gap-1 ps-5 text-p-sm text-ink-gray-7"
          >
            <li>
              {{
                __(
                  "Add the products Facebook Login for Business and Instagram API (Instagram Graph API)."
                )
              }}
            </li>
            <li>
              {{
                __(
                  "Complete Business Verification, then App Review for pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish and business_management."
                )
              }}
            </li>
            <li>
              {{
                __(
                  "Until the review passes, only people added as testers or developers of the app can connect a Page."
                )
              }}
            </li>
          </ol>
          <p class="text-p-sm text-ink-gray-6">
            {{
              __(
                "Full steps: docs/meta-publishing.md in the helpdesk repository."
              )
            }}
          </p>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { copyToClipboard } from "@/utils";
import {
  Button,
  createResource,
  ErrorMessage,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref } from "vue";
import LucideCopy from "~icons/lucide/copy";
import LucideKeyRound from "~icons/lucide/key-round";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "../SecretField.vue";
import { secretValue } from "../secretEdit";
import SettingsAction from "../SettingsAction.vue";
import SettingsSection from "../SettingsSection.vue";

interface SettingsData {
  settings: { enabled: number; app_id: string; graph_api_version: string };
  secrets: { app_secret: SecretStatus };
  redirect_url: string;
}

const form = ref<Record<string, any> | null>(null);
const initial = ref("");
const edit = ref<SecretEdit>({ mode: "keep", value: "" });
const fieldErrors = reactive({} as Record<string, string | undefined>);
// remounts the test button after a save, so an old result isn't shown for new settings
const saves = ref(0);

// HDMetaSettings.validate starts its messages with these labels
const LABELS: Record<string, string> = {
  app_id: __("App ID"),
  app_secret: __("App ID and App Secret"),
  graph_api_version: __("Graph API Version"),
};

function load(data: SettingsData) {
  const f = { ...data.settings, enabled: Boolean(data.settings.enabled) };
  form.value = f;
  initial.value = JSON.stringify(f);
  edit.value = { mode: "keep", value: "" };
  for (const key of Object.keys(LABELS)) delete fieldErrors[key];
}

const settings = createResource({
  url: "helpdesk.api.meta.get_settings",
  auto: true,
  onSuccess: load,
});

const data = computed(() => settings.data as SettingsData | undefined);
const secret = computed(
  () => data.value?.secrets.app_secret ?? { set: false, masked: "" }
);

const isDirty = computed(
  () =>
    !!form.value &&
    (JSON.stringify(form.value) !== initial.value ||
      secretValue(edit.value) !== undefined)
);

const save = createResource({
  url: "helpdesk.api.meta.save_settings",
  makeParams() {
    const values: Record<string, any> = {
      ...form.value,
      enabled: form.value?.enabled ? 1 : 0,
    };
    const secretEdit = secretValue(edit.value);
    if (secretEdit !== undefined) values.app_secret = secretEdit;
    return { values };
  },
  onSuccess(saved: SettingsData) {
    settings.setData(saved);
    load(saved);
    saves.value++;
    toast.success(__("Meta settings saved"));
  },
  onError(e: { messages?: string[] }) {
    const message = e.messages?.[0] || __("Couldn't save the Meta settings");
    for (const [key, label] of Object.entries(LABELS))
      fieldErrors[key] = message.startsWith(`${label}:`) ? message : undefined;
    toast.error(message);
  },
});
</script>
