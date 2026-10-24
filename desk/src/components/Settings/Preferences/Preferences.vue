<template>
  <SettingsLayoutBase
    :title="__('Preferences')"
    :description="
      __(
        'Your theme, language, timezone and sounds. Only you see these; a new language or timezone reloads the app.'
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
        <SettingsSection :title="__('Notifications')">
          <SettingRow
            v-slot="{ id }"
            :label="__('Sound for new tickets')"
            :description="
              __(
                'A short tone when a customer raises a ticket you take, while TBO Support is open in a tab you have used. The notice and the bell come either way.'
              )
            "
          >
            <div class="flex items-center gap-3">
              <Button
                variant="ghost"
                :label="__('Play')"
                :aria-label="__('Play the new ticket sound')"
                @click="playNotificationSound(NEW_TICKET_TONE)"
              >
                <template #prefix>
                  <LucideVolume2 class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Switch
                v-if="user.doc"
                :id="id"
                :model-value="!!user.doc.hd_new_ticket_sound"
                @update:model-value="
                  (on: boolean) => (user.doc.hd_new_ticket_sound = on ? 1 : 0)
                "
              />
            </div>
          </SettingRow>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Button, createDocumentResource, Switch, toast } from "frappe-ui";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import HDLogo from "@/assets/logos/HDLogo.vue";
import { __ } from "@/translation";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import SettingsSection from "../SettingsSection.vue";
import ThemeSwitcher from "./components/ThemeSwitcher.vue";
import LanguageTimezoneSetting from "./components/LanguageTimezoneSetting.vue";
import SettingRow from "../SettingRow.vue";
import {
  NEW_TICKET_TONE,
  playNotificationSound,
} from "@/composables/notificationSound";
import LucideVolume2 from "~icons/lucide/volume-2";

const config = useConfigStore();
const authStore = useAuthStore();
const user = createDocumentResource({
  doctype: "User",
  name: authStore.userId,
});

const needsReload = computed(
  () =>
    user.doc?.language !== user.originalDoc?.language ||
    user.doc?.time_zone !== user.originalDoc?.time_zone
);

const isDirty = computed(() => {
  if (!user.originalDoc) return false;
  return (
    needsReload.value ||
    !!user.doc?.hd_new_ticket_sound !== !!user.originalDoc?.hd_new_ticket_sound
  );
});

function save() {
  // read before saving: the saved doc becomes the new original
  const reload = needsReload.value;
  user.save.submit(null, {
    onSuccess: () => {
      toast.success(__("Preferences updated successfully."));
      // Language/timezone changes require a reload to take effect app-wide.
      if (reload) window.location.reload();
      else authStore.reloadUser();
    },
    onError: (error: { message: string; messages: string[] }) => {
      toast.error(error.message + ": " + error.messages?.[0]);
    },
  });
}
</script>
