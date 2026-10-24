<template>
  <!-- who the client is: the narrative is written from this, so presales confirms it -->
  <div class="flex flex-col gap-4">
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
      <FormControl
        :model-value="modelValue.website"
        type="url"
        :label="__('Website')"
        placeholder="https://client.example"
        maxlength="300"
        :disabled="disabled"
        @update:model-value="set('website', $event)"
      />
      <Button
        v-if="canRead"
        :label="readOn ? __('Read the website again') : __('Read the website')"
        :loading="read.loading"
        :disabled="disabled || !modelValue.website.trim()"
        @click="readSite"
      >
        <template #prefix>
          <LucideGlobe class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <p v-if="readOn" class="-mt-2 text-p-xs text-ink-gray-6">
      {{ __("Filled from the website (kept on the lead). Check it.") }}
    </p>
    <p v-if="error" role="alert" class="-mt-2 text-p-sm text-danger">
      {{ error }}
    </p>
    <FormControl
      :model-value="modelValue.about"
      type="textarea"
      :rows="2"
      :label="__('What they do')"
      maxlength="1000"
      :disabled="disabled"
      @update:model-value="set('about', $event)"
    />
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <FormControl
        data-profile-field="industry"
        :model-value="modelValue.industry"
        :label="__('Industry')"
        required
        maxlength="1000"
        :disabled="disabled"
        @update:model-value="set('industry', $event)"
      />
      <FormControl
        :model-value="modelValue.size"
        :label="__('Size / users')"
        maxlength="1000"
        :disabled="disabled"
        @update:model-value="set('size', $event)"
      />
      <FormControl
        :model-value="modelValue.locations"
        :label="__('Locations')"
        maxlength="1000"
        :disabled="disabled"
        @update:model-value="set('locations', $event)"
      />
    </div>
    <FormControl
      :model-value="modelValue.current_software"
      :label="__('Current software')"
      :placeholder="__('e.g. Tally, Excel, a biometric device')"
      maxlength="1000"
      :disabled="disabled"
      @update:model-value="set('current_software', $event)"
    />
    <FormControl
      :model-value="modelValue.key_processes"
      type="textarea"
      :rows="2"
      :label="__('Key processes')"
      maxlength="1000"
      :disabled="disabled"
      @update:model-value="set('key_processes', $event)"
    />
    <FormControl
      data-profile-field="pain_points"
      :model-value="modelValue.pain_points"
      type="textarea"
      :rows="3"
      :label="__('Pain points')"
      :description="
        __(
          'Only what the client told us: the challenges are written from this.'
        )
      "
      required
      maxlength="1000"
      :disabled="disabled"
      @update:model-value="set('pain_points', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl } from "frappe-ui";
import { ref } from "vue";
import LucideGlobe from "~icons/lucide/globe";
import type { ClientProfile } from "./proposals";

const props = defineProps<{
  modelValue: ClientProfile;
  lead: string;
  /** the AI is on: the website can be read */
  canRead?: boolean;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: ClientProfile): void;
}>();

const error = ref("");
const readOn = ref(false);

function set<K extends keyof ClientProfile>(key: K, value: string) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}

const read = createResource({
  url: "helpdesk.api.proposals.read_client_website",
  method: "POST",
  onSuccess(d: { profile: Partial<ClientProfile> }) {
    const next = { ...props.modelValue };
    for (const [key, value] of Object.entries(d.profile || {}))
      if (value && key in next) next[key as keyof ClientProfile] = value;
    emit("update:modelValue", next);
    readOn.value = true;
  },
  onError(e: unknown) {
    error.value = errorText(
      e,
      __("Couldn't read the website. Type the profile instead.")
    );
  },
});

function readSite() {
  error.value = "";
  read.submit({
    lead: props.lead,
    url: props.modelValue.website,
    refresh: readOn.value ? 1 : 0,
  });
}
</script>
