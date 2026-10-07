<template>
  <SettingsLayoutBase
    :title="__('Preferences')"
    :description="
      __(
        'Your theme, language and timezone. Only you see these; saving reloads the app.'
      )
    "
    :dirty="isDirty"
    :saving="user.save.loading"
    :loading="user.get.loading && !user.doc"
    :error="user.get.error"
    @retry="user.reload()"
    @save="save"
  >
    <template #content>
      <div>
        <SettingsSection
          :title="__('Appearance')"
          :description="__('The theme changes straight away.')"
        >
          <ThemeSwitcher
            :name="config.brandName"
            :logo="config.brandLogo || HDLogo"
          />
        </SettingsSection>
        <SettingsSection :title="__('Language and time')">
          <LanguageTimezoneSetting :user="user" />
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { createDocumentResource, toast } from "frappe-ui";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import HDLogo from "@/assets/logos/HDLogo.vue";
import { __ } from "@/translation";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import SettingsSection from "../SettingsSection.vue";
import ThemeSwitcher from "./components/ThemeSwitcher.vue";
import LanguageTimezoneSetting from "./components/LanguageTimezoneSetting.vue";

const config = useConfigStore();
const { userId } = useAuthStore();
const user = createDocumentResource({ doctype: "User", name: userId });

const isDirty = computed(() => {
  if (!user.originalDoc) return false;
  return (
    user.doc?.language !== user.originalDoc?.language ||
    user.doc?.time_zone !== user.originalDoc?.time_zone
  );
});

function save() {
  user.save.submit(null, {
    onSuccess: () => {
      toast.success(__("Preferences updated successfully."));
      // Language/timezone changes require a reload to take effect app-wide.
      window.location.reload();
    },
    onError: (error: { message: string; messages: string[] }) => {
      toast.error(error.message + ": " + error.messages?.[0]);
    },
  });
}
</script>
