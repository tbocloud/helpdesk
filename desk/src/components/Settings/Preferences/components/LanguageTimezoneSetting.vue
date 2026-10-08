<template>
  <SettingRow
    v-slot="{ id, labelledby }"
    :label="__('Language')"
    :description="__('Change language of the application.')"
  >
    <Link
      :id="id"
      :labelledby="labelledby"
      :model-value="user.doc?.language"
      doctype="Language"
      class="w-full sm:w-48"
      :placeholder="__('Select language')"
      @update:model-value="updateLanguage"
    />
  </SettingRow>
  <SettingRow
    v-slot="{ id, labelledby }"
    :label="__('Timezone')"
    :description="__('Change timezone of the application.')"
  >
    <Autocomplete
      :id="id"
      :labelledby="labelledby"
      :model-value="user.doc?.time_zone"
      :options="timezoneOptions"
      :placeholder="__('Select Timezone')"
      size="sm"
      class="w-full sm:w-48"
      @update:model-value="updateTimezone"
    />
  </SettingRow>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { createResource } from "frappe-ui";
import { __ } from "@/translation";
import SettingRow from "../../SettingRow.vue";

const props = defineProps<{ user: any }>();

function updateLanguage(value: string | null) {
  if (!props.user.doc) return;
  props.user.doc.language = value || props.user.originalDoc?.language;
}

function updateTimezone(value: { label: string; value: string } | null) {
  if (!props.user.doc) return;
  props.user.doc.time_zone = value?.value || props.user.originalDoc?.time_zone;
}

const timezoneOptions = ref<{ label: string; value: string }[]>([]);
createResource({
  url: "frappe.core.doctype.user.user.get_timezones",
  auto: true,
  onSuccess(data: { timezones: string[] }) {
    timezoneOptions.value = data.timezones.map((tz) => ({
      label: tz,
      value: tz,
    }));
  },
});
</script>
