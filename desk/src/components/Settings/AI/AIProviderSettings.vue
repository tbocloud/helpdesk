<template>
  <SettingsLayoutBase
    :title="__('AI providers')"
    :description="
      __(
        'Which AI writes triage, reply drafts, task descriptions and summaries, and which one takes over when it fails.'
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
        <AIProviderBanner
          v-if="status"
          class="mb-6"
          :status="status"
          show-setup
        />

        <div>
          <SettingsSection :title="__('Order')">
            <SettingRow
              v-slot="{ id }"
              :label="__('Primary provider')"
              :description="__('Tried first for every AI call.')"
            >
              <FormControl
                :id="id"
                v-model="form.primary_ai_provider"
                type="select"
                class="w-full sm:w-56"
                :options="SLOTS"
              />
            </SettingRow>
            <SettingRow
              v-slot="{ id }"
              :label="__('Fall back to the other provider')"
              :description="
                __(
                  'When the primary runs out of balance or quota, refuses its key, can\'t find the model, has a server error or doesn\'t answer in time. A provider with a billing, key or model problem is then skipped for 30 minutes, and System and Agent Managers are told once.'
                )
              "
            >
              <Switch :id="id" v-model="form.ai_failover" />
            </SettingRow>
          </SettingsSection>

          <SettingsSection
            v-for="section in SECTIONS"
            :key="section.slot"
            :title="section.title"
            :description="section.description"
          >
            <template #actions>
              <TaskyBadge
                v-for="badge in badges(section.slot)"
                :key="badge.label"
                :label="badge.label"
                :tone="badge.tone"
                :icon="badge.icon"
              />
            </template>
            <div class="grid gap-4 sm:grid-cols-2">
              <div class="flex min-w-0 flex-col gap-1.5">
                <FormControl
                  v-model="form[section.model]"
                  :label="__('Model')"
                  :description="section.modelHelp"
                  :placeholder="section.modelPlaceholder"
                  autocomplete="off"
                  spellcheck="false"
                />
              </div>
              <div class="flex min-w-0 flex-col gap-1.5">
                <FormControl
                  v-model="form[section.baseUrl]"
                  :label="__('Base URL')"
                  :description="section.baseUrlHelp"
                  :placeholder="section.baseUrlPlaceholder"
                  autocomplete="off"
                  spellcheck="false"
                />
                <ErrorMessage
                  v-if="fieldErrors[section.baseUrl]"
                  role="alert"
                  :message="fieldErrors[section.baseUrl]"
                />
              </div>
            </div>
            <SecretField
              v-model="edits[section.key]"
              :label="__('API key')"
              :description="
                __(
                  'Stored only on this hub, encrypted. Once saved it is never shown again.'
                )
              "
              :status="secrets[section.key]"
              type="password"
              :placeholder="section.keyPlaceholder"
              removable
            >
              <SettingsAction
                v-if="secrets[section.key]?.set"
                :key="`${section.slot}-${saves}`"
                method="helpdesk.api.ai_settings.test_connection"
                :params="{ provider: section.slot }"
                :label="__('Test connection')"
                :icon="LucidePlugZap"
                :unsaved="isDirty"
                @done="refreshStatus"
              />
            </SecretField>
          </SettingsSection>
        </div>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import AIProviderBanner from "@/components/AIProviderBanner.vue";
import type { ProviderSlot, ProviderStatus } from "@/components/aiProviders";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import {
  createResource,
  ErrorMessage,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, type Component } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucidePause from "~icons/lucide/pause";
import LucidePlugZap from "~icons/lucide/plug-zap";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "../SecretField.vue";
import { secretValue } from "../secretEdit";
import SettingRow from "../SettingRow.vue";
import SettingsAction from "../SettingsAction.vue";
import SettingsSection from "../SettingsSection.vue";

const SLOTS: ProviderSlot[] = ["OpenAI", "Anthropic-compatible"];
const SECRETS = ["openai_api_key", "anthropic_api_key"] as const;
type Secret = typeof SECRETS[number];
type BaseUrlField = "openai_base_url" | "ai_base_url";

// HDSHubSettings.validate starts its messages with these labels
const LABELS: Record<BaseUrlField, string> = {
  openai_base_url: __("OpenAI Base URL"),
  ai_base_url: __("Base URL"),
};

interface Section {
  slot: ProviderSlot;
  title: string;
  description: string;
  model: string;
  modelHelp: string;
  modelPlaceholder?: string;
  baseUrl: BaseUrlField;
  baseUrlHelp: string;
  baseUrlPlaceholder: string;
  key: Secret;
  keyPlaceholder: string;
}

const SECTIONS: Section[] = [
  {
    slot: "OpenAI",
    title: __("OpenAI"),
    description: __("GPT models through OpenAI's Chat Completions API."),
    model: "openai_model",
    modelHelp: __(
      "Must match the model ID shown in your OpenAI dashboard exactly. Test the connection after saving."
    ),
    modelPlaceholder: __("The model ID from your OpenAI dashboard"),
    baseUrl: "openai_base_url",
    baseUrlHelp: __(
      "Empty: OpenAI. Another OpenAI-compatible endpoint works too."
    ),
    baseUrlPlaceholder: "https://api.openai.com/v1",
    key: "openai_api_key",
    keyPlaceholder: "sk-proj-…",
  },
  {
    slot: "Anthropic-compatible",
    title: __("Anthropic-compatible"),
    description: __(
      "Anthropic, or a provider with the same API, such as Kimi (Moonshot) or GLM."
    ),
    model: "default_triage_model",
    modelHelp: __("For example kimi-k2.6 on Kimi."),
    baseUrl: "ai_base_url",
    baseUrlHelp: __(
      "Empty: Anthropic's own API. Kimi: https://api.moonshot.ai/anthropic."
    ),
    baseUrlPlaceholder: "https://api.anthropic.com",
    key: "anthropic_api_key",
    keyPlaceholder: "sk-…",
  },
];

interface SettingsData {
  settings: Record<string, any>;
  secrets: Record<Secret, SecretStatus>;
  status: ProviderStatus;
}

const form = ref<Record<string, any> | null>(null);
const initial = ref("");
const edits = reactive({} as Record<Secret, SecretEdit>);
const fieldErrors = reactive({} as Partial<Record<BaseUrlField, string>>);
// remounts the test buttons after a save, so an old result isn't shown for new settings
const saves = ref(0);

function load(data: SettingsData) {
  form.value = {
    ...data.settings,
    ai_failover: Boolean(data.settings.ai_failover),
  };
  initial.value = JSON.stringify(form.value);
  for (const key of SECRETS) edits[key] = { mode: "keep", value: "" };
  for (const key of Object.keys(LABELS)) delete fieldErrors[key];
}

const settings = createResource({
  url: "helpdesk.api.ai_settings.get_settings",
  auto: true,
  onSuccess: load,
});

const data = computed(() => settings.data as SettingsData | undefined);
const secrets = computed(
  () => data.value?.secrets ?? ({} as Record<Secret, SecretStatus>)
);
const status = computed(() => data.value?.status);

/** A test changes the provider's state (unpaused, failing); show it without
 * touching the form, which is saved whenever a test can run. */
function refreshStatus() {
  settings.reload();
}

interface Badge {
  label: string;
  tone: Tone;
  icon?: Component;
}

function badges(slot: ProviderSlot): Badge[] {
  const s = status.value;
  const state = s?.providers[slot];
  if (!s || !state) return [];
  const result: Badge[] = [];
  if (s.primary === slot)
    result.push({ label: __("Primary"), tone: "neutral" });
  else if (s.failover) result.push({ label: __("Fallback"), tone: "neutral" });
  else result.push({ label: __("Not used"), tone: "neutral" });
  if (!state.configured)
    result.push({ label: __("Not set up"), tone: "neutral" });
  else if (state.paused)
    result.push({ label: __("Paused"), tone: "danger", icon: LucidePause });
  else if (state.down)
    result.push({ label: __("Failing"), tone: "danger", icon: LucideCircleX });
  else if (s.in_use === slot)
    result.push({
      label: __("Answering"),
      tone: "success",
      icon: LucideCircleCheck,
    });
  return result;
}

/** What a key's edit sends: a new value, "" to remove it, or nothing. */
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
  url: "helpdesk.api.ai_settings.save_settings",
  makeParams() {
    const values: Record<string, any> = {
      ...form.value,
      ai_failover: form.value?.ai_failover ? 1 : 0,
    };
    for (const key of SECRETS) {
      const value = secretParam(key);
      if (value !== undefined) values[key] = value;
    }
    return { values };
  },
  onSuccess(saved: SettingsData) {
    settings.setData(saved);
    load(saved);
    saves.value++;
    toast.success(__("AI providers saved"));
  },
  onError(e: { messages?: string[] }) {
    const message = e.messages?.[0] || __("Couldn't save the AI providers");
    for (const [key, label] of Object.entries(LABELS))
      fieldErrors[key] = message.startsWith(`${label}:`) ? message : undefined;
    toast.error(message);
  },
});
</script>
