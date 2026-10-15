<template>
  <SettingsSection
    v-if="settingsData && authStore.isAdmin"
    :title="__('Offboarding')"
    :description="
      __(
        'Microsoft is the only sign-in for TBO staff. Someone disabled or deleted there loses this site too.'
      )
    "
  >
    <SettingRow
      v-slot="{ id }"
      :label="__('Disable people removed from Microsoft')"
      :description="
        __(
          'Every hour, disable each enabled user at the company domains whose Microsoft account is disabled or gone. System Managers are never touched. Reads the directory with the Microsoft app in HD Meeting Settings, which needs the User.Read.All permission.'
        )
      "
    >
      <Switch :id="id" v-model="settingsData.offboardRemovedMicrosoftUsers" />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Company email domains')"
      :description="__('One per line, e.g. teambackoffice.com.')"
    >
      <FormControl
        :id="id"
        v-model="settingsData.offboardingDomains"
        type="textarea"
        :rows="2"
        class="w-full font-mono sm:w-80"
        autocomplete="off"
        spellcheck="false"
      />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Dry run')"
      :description="__('Find who would be disabled without changing anyone.')"
    >
      <Switch :id="id" v-model="settingsData.offboardingDryRun" />
    </SettingRow>
    <SettingRow
      v-slot="{ id }"
      :label="__('Most people disabled per run')"
      :description="
        __(
          'Above this, nobody is disabled and System Managers are alerted instead.'
        )
      "
    >
      <FormControl
        :id="id"
        v-model="settingsData.offboardingMaxDisables"
        type="number"
        min="1"
        class="w-full font-mono tabular-nums sm:w-24"
      />
    </SettingRow>

    <div class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <Button
          :label="__('Preview')"
          :loading="preview.loading"
          :disabled="dirty || run.loading"
          :tooltip="dirty ? __('Save your changes first') : ''"
          @click="submit(preview)"
        >
          <template #prefix>
            <LucideEye class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          :label="__('Run now')"
          :loading="run.loading"
          :disabled="Boolean(runBlocked) || preview.loading"
          :tooltip="runBlocked"
          @click="submit(run)"
        >
          <template #prefix>
            <LucidePlay class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>

      <p
        v-if="error"
        role="alert"
        class="flex items-start gap-1.5 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ error }}</span>
      </p>
      <template v-else-if="result && summary">
        <p
          role="status"
          class="flex items-start gap-1.5 text-p-sm"
          :class="INK[summary.tone]"
        >
          <component
            :is="summary.icon"
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>{{ summary.text }}</span>
        </p>
        <SettingsList
          v-if="result.people.length"
          :items="result.people"
          :label="__('People found')"
          row-key="user"
          :empty-icon="LucideUserCheck"
          :empty-title="__('Nobody')"
        >
          <template #default="{ item }">
            <PersonRow :person="item" />
          </template>
        </SettingsList>
      </template>
    </div>

    <div class="flex flex-col gap-2">
      <h3 class="text-base-medium text-ink-gray-8">
        {{ __("Recently disabled") }}
      </h3>
      <SettingsList
        :items="log.data"
        :label="__('Recently disabled')"
        :loading="log.loading"
        :error="log.error"
        row-key="name"
        :empty-icon="LucideUserCheck"
        :empty-title="__('Nobody disabled yet')"
        :empty-message="
          __('People offboarding disables are listed here, with the reason.')
        "
        @retry="log.reload()"
      >
        <template #default="{ item }">
          <PersonRow :person="item" />
        </template>
      </SettingsList>
    </div>
  </SettingsSection>
</template>

<script setup lang="ts">
import { INK, type Tone } from "@/components/tone";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { HDSettingsSymbol } from "@/types";
import { errorText } from "@/utils";
import {
  Button,
  createListResource,
  createResource,
  FormControl,
  Switch,
} from "frappe-ui";
import { computed, inject, ref, type Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideEye from "~icons/lucide/eye";
import LucideInfo from "~icons/lucide/info";
import LucidePlay from "~icons/lucide/play";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUserCheck from "~icons/lucide/user-check";
import SettingRow from "../../SettingRow.vue";
import SettingsList from "../../SettingsList.vue";
import SettingsSection from "../../SettingsSection.vue";
import PersonRow from "./OffboardingPersonRow.vue";

const props = defineProps<{
  /** Preview and Run now use the saved settings, so they wait for a save. */
  dirty?: boolean;
}>();

interface Result {
  status: "dry_run" | "capped" | "done";
  people: { user: string; full_name: string; reason: string }[];
  cap: number;
}

const settingsData = inject(HDSettingsSymbol);
const authStore = useAuthStore();

const result = ref<Result | null>(null);
const error = ref("");

const preview = createResource({
  url: "helpdesk.api.offboarding.preview_offboarding",
});
const run = createResource({ url: "helpdesk.api.offboarding.run_offboarding" });

const log = createListResource({
  doctype: "HD Offboarding Log",
  fields: ["name", "user", "full_name", "reason", "disabled_on"],
  // removals from TBO Chat are logged here too, but this list is who was disabled
  filters: { action: "Disabled in TBO Support" },
  orderBy: "disabled_on desc",
  pageLength: 10,
  auto: authStore.isAdmin,
});

const runBlocked = computed(() => {
  if (props.dirty) return __("Save your changes first");
  if (!settingsData.value.offboardRemovedMicrosoftUsers)
    return __("Turn on Disable people removed from Microsoft and save first");
  return "";
});

async function submit(resource: typeof preview) {
  error.value = "";
  result.value = null;
  try {
    result.value = await resource.submit();
  } catch (e) {
    error.value = errorText(e, __("Couldn't reach Microsoft. Try again."));
  }
  if (resource === run) log.reload();
}

const summary = computed<{
  tone: Tone;
  icon: Component;
  text: string;
} | null>(() => {
  if (!result.value) return null;
  const { status, people, cap } = result.value;
  const count = people.length;
  if (status === "capped")
    return {
      tone: "warning",
      icon: LucideTriangleAlert,
      text: __(
        "Stopped: {0} people would be disabled, more than the limit of {1}. Nobody was changed; System Managers were alerted.",
        [count, cap]
      ),
    };
  if (status === "done")
    return count
      ? {
          tone: "success",
          icon: LucideCircleCheck,
          text: __("Disabled {0} people. Agent Managers were told.", [count]),
        }
      : {
          tone: "success",
          icon: LucideCircleCheck,
          text: __("Everyone is still in Microsoft. Nobody was disabled."),
        };
  if (!count)
    return {
      tone: "neutral",
      icon: LucideInfo,
      text: __("Everyone is still in Microsoft. Nobody would be disabled."),
    };
  if (count > cap)
    return {
      tone: "warning",
      icon: LucideTriangleAlert,
      text: __(
        "{0} people would be disabled, more than the limit of {1}: a run would stop and alert System Managers.",
        [count, cap]
      ),
    };
  return {
    tone: "neutral",
    icon: LucideInfo,
    text: __("{0} people would be disabled. Nobody was changed.", [count]),
  };
});
</script>
