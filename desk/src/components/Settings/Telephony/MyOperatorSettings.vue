<template>
  <SettingsLayoutBase
    :title="__('MyOperator')"
    :description="
      __(
        'Calls with leads through MyOperator: Call on a lead, every call on its timeline with the recording, and an AI summary. Saved on the ERP site.'
      )
    "
    :back-label="canGoBack ? __('Back to telephony') : undefined"
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @back="emit('updateStep', 'telephony-settings')"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template #content>
      <div v-if="form && data">
        <SettingsSection :title="__('Calling')">
          <SettingRow
            v-slot="{ id }"
            :label="__('Use MyOperator')"
            :description="
              __(
                'Off: MyOperator\'s webhooks are refused and nobody sees Call.'
              )
            "
          >
            <Switch :id="id" v-model="form.enable_telephony" />
          </SettingRow>
          <div class="grid gap-4 sm:grid-cols-3">
            <FormControl
              v-model="form.myoperator_company_id"
              :label="__('Company ID')"
              autocomplete="off"
              spellcheck="false"
            />
            <FormControl
              v-model="form.myoperator_public_ivr_id"
              :label="__('Public IVR ID')"
              :description="__('The IVR click-to-call goes through.')"
              autocomplete="off"
              spellcheck="false"
            />
            <FormControl
              v-model="form.myoperator_caller_id"
              :label="__('Caller ID (optional)')"
              :description="__('The number leads see.')"
              autocomplete="off"
              spellcheck="false"
            />
          </div>
          <p class="max-w-prose text-p-sm text-ink-gray-6">
            {{
              __(
                "In MyOperator: APIs & Webhook → Developer API → Calling APIs → Endpoint details."
              )
            }}
          </p>
          <SecretField
            v-for="secret in SECRETS"
            :key="secret.key"
            v-model="edits[secret.key]"
            :label="secret.label"
            :description="secret.description"
            :status="secretStatus(secret.key)"
            type="password"
            removable
          />
          <SettingsAction
            :key="`test-${saves}`"
            method="helpdesk.api.myoperator.test_connection"
            :label="__('Test connection')"
            :icon="LucidePlugZap"
            :unsaved="isDirty"
            @done="onTested"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Webhook')"
          :description="
            __(
              'Paste these into MyOperator → Webhooks v2, so every call lands on its lead.'
            )
          "
        >
          <dl
            class="grid grid-cols-1 gap-x-4 gap-y-3 text-p-sm sm:grid-cols-[10rem_minmax(0,1fr)]"
          >
            <dt class="text-ink-gray-6">{{ __("URL (POST, JSON)") }}</dt>
            <dd class="flex min-w-0 items-center gap-2">
              <span class="min-w-0 break-all font-mono text-ink-gray-8">{{
                data.webhook.url
              }}</span>
              <Button
                variant="ghost"
                :aria-label="__('Copy the webhook URL')"
                @click="copyToClipboard(data.webhook.url)"
              >
                <template #icon>
                  <LucideCopy class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </dd>
            <dt class="text-ink-gray-6">{{ __("Header") }}</dt>
            <dd class="font-mono text-ink-gray-8">
              {{ data.webhook.header }}:
              <span class="text-ink-gray-6">{{
                secretStatus("telephony_webhook_secret").set
                  ? __(
                      "the webhook secret ({0})",
                      secretStatus("telephony_webhook_secret").masked || "…"
                    )
                  : __("not made yet")
              }}</span>
            </dd>
            <dt class="text-ink-gray-6">{{ __("Events") }}</dt>
            <dd class="font-mono text-ink-gray-8">
              {{ data.webhook.events.join(", ") }}
            </dd>
          </dl>
          <div
            v-if="newSecret"
            role="status"
            class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-3"
          >
            <p class="text-p-sm text-ink-gray-8">
              {{
                __(
                  "The new secret. Copy it into MyOperator now: it isn't shown again, and calls are refused until MyOperator sends it."
                )
              }}
            </p>
            <div class="flex min-w-0 items-center gap-2">
              <span
                class="min-w-0 flex-1 break-all rounded border border-outline-gray-2 bg-surface-base px-2 py-1.5 font-mono text-sm text-ink-gray-9"
                >{{ newSecret }}</span
              >
              <Button :label="__('Copy')" @click="copyToClipboard(newSecret)">
                <template #prefix>
                  <LucideCopy class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>
          <div>
            <Button
              :label="
                secretStatus('telephony_webhook_secret').set
                  ? __('Make a new secret')
                  : __('Make the webhook secret')
              "
              :loading="regenerate.loading"
              @click="confirmRegenerate"
            >
              <template #prefix>
                <LucideKeyRound class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('People')"
          :description="
            __(
              'Who each MyOperator user is. Call rings the person\'s MyOperator user, or their mobile; a call\'s agent is found by user ID, extension or mobile.'
            )
          "
        >
          <template #actions>
            <Button :label="__('Add person')" @click="addAgent">
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
          <p v-if="!form.agents.length" class="text-p-sm text-ink-gray-6">
            {{
              __(
                "Nobody yet. Test the connection to see MyOperator's users and their IDs."
              )
            }}
          </p>
          <ul v-else role="list" class="flex flex-col gap-3">
            <li
              v-for="(agent, i) in form.agents"
              :key="i"
              class="grid grid-cols-1 items-end gap-3 rounded-lg border border-outline-gray-2 p-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1.4fr)_6rem_minmax(0,1fr)_auto]"
            >
              <FormControl
                v-model="agent.user"
                type="select"
                :label="__('Person')"
                :options="userOptions"
              />
              <FormControl
                v-if="moUsers.length"
                v-model="agent.myoperator_user_id"
                type="select"
                :label="__('MyOperator user')"
                :options="moUserOptions"
              />
              <FormControl
                v-else
                v-model="agent.myoperator_user_id"
                :label="__('MyOperator user ID')"
                autocomplete="off"
                spellcheck="false"
              />
              <FormControl
                v-model="agent.extension"
                :label="__('Extension')"
                autocomplete="off"
              />
              <FormControl
                v-model="agent.mobile"
                type="tel"
                :label="__('Mobile')"
                autocomplete="off"
              />
              <Button
                variant="ghost"
                :aria-label="__('Remove {0}', agent.user || __('this person'))"
                @click="form.agents.splice(i, 1)"
              >
                <template #icon>
                  <LucideTrash2 class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </li>
          </ul>
        </SettingsSection>

        <SettingsSection :title="__('Unknown callers')">
          <SettingRow
            v-slot="{ id }"
            :label="__('Make a lead for an unknown caller')"
            :description="
              __(
                'An incoming call from a number no lead has becomes a new lead, source Phone call.'
              )
            "
          >
            <Switch :id="id" v-model="form.telephony_create_leads" />
          </SettingRow>
          <FormControl
            v-model="form.telephony_fallback_owner"
            type="select"
            class="sm:max-w-sm"
            :label="__('Owner when nobody here answered')"
            :options="[
              { label: __('The smart leads fallback owner'), value: '' },
              ...userOptions,
            ]"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Recordings')"
          :description="
            __(
              'Recordings play only to people who may see the lead. Older ones are deleted every night; the call and its summary stay.'
            )
          "
        >
          <FormControl
            v-model.number="form.telephony_recording_days"
            type="number"
            min="1"
            class="sm:max-w-[12rem]"
            :label="__('Keep recordings (days)')"
          />
          <FormControl
            v-model="form.telephony_recording_notice"
            type="textarea"
            :rows="2"
            :label="__('Recording notice')"
            :description="
              __(
                'Set this as the greeting of every MyOperator number and IVR, so callers hear it before a recorded call. The DPDP Act asks you to tell people before you record them.'
              )
            "
          />
        </SettingsSection>

        <SettingsSection
          :title="__('AI call summary')"
          :description="
            __(
              'Transcribes an answered call (Malayalam, English or both) with the OpenAI provider in the ERP site\'s AI settings and sums it up on the lead. Each call takes one of the day\'s AI lead reads.'
            )
          "
        >
          <SettingRow v-slot="{ id }" :label="__('Sum up calls')">
            <Switch :id="id" v-model="form.enable_call_summary" />
          </SettingRow>
          <div class="grid gap-4 sm:grid-cols-3">
            <FormControl
              v-model.number="form.call_summary_min_seconds"
              type="number"
              min="0"
              :label="__('Shortest call (seconds)')"
            />
            <FormControl
              v-model="form.transcription_model"
              :label="__('Transcription model')"
              placeholder="gpt-4o-transcribe"
              autocomplete="off"
              spellcheck="false"
            />
            <FormControl
              v-model.number="form.transcription_price_per_minute"
              type="number"
              min="0"
              step="any"
              :label="__('Price per minute (USD)')"
            />
          </div>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
  <ConfirmDialog
    v-model="confirmNewSecret"
    :title="__('Make a new webhook secret?')"
    :message="
      __(
        'MyOperator\'s webhooks are refused until you paste the new secret there.'
      )
    "
    :on-confirm="
      () => {
        confirmNewSecret = false;
        regenerate.submit();
      }
    "
    :on-cancel="() => (confirmNewSecret = false)"
  />
</template>

<script setup lang="ts">
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { copyToClipboard, errorText } from "@/utils";
import { Button, createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, reactive, ref } from "vue";
import LucideCopy from "~icons/lucide/copy";
import LucideKeyRound from "~icons/lucide/key-round";
import LucidePlugZap from "~icons/lucide/plug-zap";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "../SecretField.vue";
import { secretValue } from "../secretEdit";
import SettingRow from "../SettingRow.vue";
import SettingsAction from "../SettingsAction.vue";
import SettingsSection from "../SettingsSection.vue";

const emit = defineEmits<{ updateStep: [step: string] }>();

const auth = useAuthStore();
// with the telephony app the page has Twilio and Exotel too, and this is one of them
const canGoBack = computed(() => auth.telephonyInstalled);

type Secret =
  | "myoperator_api_key"
  | "myoperator_secret_token"
  | "myoperator_api_token";

const SECRETS: { key: Secret; label: string; description: string }[] = [
  {
    key: "myoperator_api_key",
    label: __("Calling API key (x-api-key)"),
    description: __("Places the calls Call asks for."),
  },
  {
    key: "myoperator_secret_token",
    label: __("Calling secret token"),
    description: __("Sent with every call request."),
  },
  {
    key: "myoperator_api_token",
    label: __("API token"),
    description: __(
      "Fetches each call's recording and lists MyOperator's users. Once saved, none of these are shown again."
    ),
  },
];

interface Agent {
  user: string;
  myoperator_user_id: string;
  extension: string;
  mobile: string;
}

interface SettingsData {
  settings: Record<string, any>;
  agents: Partial<Agent>[];
  secrets: Record<string, SecretStatus>;
  webhook: { url: string; header: string; events: string[] };
  users: { email: string; full_name?: string }[];
}

interface MyOperatorUser {
  uuid: string;
  name?: string;
  extension?: string;
  contact?: string;
}

const form = ref<(Record<string, any> & { agents: Agent[] }) | null>(null);
const initial = ref("");
const edits = reactive({} as Record<Secret, SecretEdit>);
const saves = ref(0);
const moUsers = ref<MyOperatorUser[]>([]);
const newSecret = ref("");

const SWITCHES = [
  "enable_telephony",
  "telephony_create_leads",
  "enable_call_summary",
];

function load(d: SettingsData) {
  const values: Record<string, any> = { ...d.settings };
  for (const key of SWITCHES) values[key] = Boolean(values[key]);
  values.telephony_fallback_owner = values.telephony_fallback_owner || "";
  form.value = {
    ...values,
    agents: d.agents.map((a) => ({
      user: a.user || "",
      myoperator_user_id: a.myoperator_user_id || "",
      extension: a.extension || "",
      mobile: a.mobile || "",
    })),
  };
  initial.value = JSON.stringify(form.value);
  for (const s of SECRETS) edits[s.key] = { mode: "keep", value: "" };
}

const settings = createResource({
  url: "helpdesk.api.myoperator.get_settings",
  auto: true,
  onSuccess: load,
});
const data = computed(() => settings.data as SettingsData | undefined);

function secretStatus(key: string): SecretStatus {
  return data.value?.secrets?.[key] ?? { set: false, masked: "" };
}

const userOptions = computed(() => [
  { label: __("Pick a person"), value: "" },
  ...(data.value?.users ?? []).map((u) => ({
    label: u.full_name ? `${u.full_name} (${u.email})` : u.email,
    value: u.email,
  })),
]);

const moUserOptions = computed(() => [
  { label: __("None: ring the mobile"), value: "" },
  ...moUsers.value.map((u) => ({
    label: [u.name, u.extension && `ext. ${u.extension}`]
      .filter(Boolean)
      .join(" · "),
    value: u.uuid,
  })),
]);

function onTested(result: { users?: MyOperatorUser[] }) {
  moUsers.value = (result.users ?? []).filter((u) => u.uuid);
}

function addAgent() {
  form.value?.agents.push({
    user: "",
    myoperator_user_id: "",
    extension: "",
    mobile: "",
  });
}

const isDirty = computed(
  () =>
    !!form.value &&
    (JSON.stringify(form.value) !== initial.value ||
      SECRETS.some((s) => secretValue(edits[s.key]) !== undefined))
);

const save = createResource({
  url: "helpdesk.api.myoperator.save_settings",
  makeParams() {
    const values: Record<string, any> = { ...form.value };
    for (const key of SWITCHES) values[key] = values[key] ? 1 : 0;
    values.agents = (form.value?.agents ?? []).filter((a) => a.user);
    for (const s of SECRETS) {
      const value = secretValue(edits[s.key]);
      if (value !== undefined) values[s.key] = value;
    }
    return { values };
  },
  onSuccess(saved: SettingsData) {
    settings.setData(saved);
    load(saved);
    saves.value++;
    toast.success(__("MyOperator settings saved"));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save the MyOperator settings")));
  },
});

const regenerate = createResource({
  url: "helpdesk.api.myoperator.regenerate_webhook_secret",
  onSuccess(result: { secret: string }) {
    newSecret.value = result.secret;
    // only the secret's state changes: unsaved edits on the page stay
    if (data.value)
      settings.setData({
        ...data.value,
        secrets: {
          ...data.value.secrets,
          telephony_webhook_secret: {
            set: true,
            masked: `…${result.secret.slice(-4)}`,
          },
        },
      });
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't make a new secret")));
  },
});

const confirmNewSecret = ref(false);

function confirmRegenerate() {
  if (secretStatus("telephony_webhook_secret").set)
    confirmNewSecret.value = true;
  else regenerate.submit();
}
</script>
