<template>
  <SettingsLayoutBase
    :title="__('Profile')"
    :description="__('Your photo, availability, emails and password.')"
  >
    <template #content>
      <div>
        <SettingsSection :title="__('Photo')">
          <FileUploader
            :fileTypes="['image/*']"
            @success="
              (file) => {
                updateImage(file.file_url);
              }
            "
          >
            <template #default="{ openFileSelector, uploading }">
              <div class="flex min-w-0 items-center gap-4">
                <div class="group relative size-16 shrink-0">
                  <Avatar
                    class="!size-16"
                    :image="user.doc?.user_image"
                    :label="fullName"
                  />
                  <div
                    v-if="agentStatusStore.myStatus"
                    class="absolute bottom-0.5 right-0.5 rounded-full bg-surface-elevation-2 p-1"
                  >
                    <div
                      class="size-3.5 rounded-full"
                      :class="
                        agentStatusStore.statusColor(agentStatusStore.myStatus)
                      "
                    />
                  </div>
                  <Tooltip
                    :hoverDelay="0"
                    placement="bottom"
                    :text="profileTooltipText"
                  >
                    <button
                      type="button"
                      class="absolute left-0 top-0 !size-16 rounded-full"
                      :aria-label="profileTooltipText"
                      @click.stop="openFileSelector"
                    />
                    <button
                      v-if="user.doc?.user_image"
                      type="button"
                      class="absolute -right-1 -top-1 flex size-5 items-center justify-center rounded-full bg-surface-base shadow-sm ring-1 ring-outline-gray-2 duration-300 ease-in-out hover:bg-surface-gray-2 sm:opacity-0 sm:focus-visible:opacity-100 sm:group-hover:opacity-100"
                      :aria-label="__('Remove Photo')"
                      @click.stop="updateImage()"
                      @mouseenter="isHoveringRemove = true"
                      @mouseleave="isHoveringRemove = false"
                    >
                      <LucideX
                        class="size-3.5 text-ink-gray-6"
                        aria-hidden="true"
                      />
                    </button>
                  </Tooltip>
                  <div
                    v-if="uploading"
                    class="absolute left-0 top-0 flex h-full w-full items-center justify-center rounded-full bg-surface-gray-10 bg-opacity-20"
                  >
                    <LoadingIndicator class="size-4" />
                  </div>
                </div>
                <div class="flex min-w-0 flex-col gap-0.5">
                  <span class="truncate text-lg-semibold text-ink-gray-9">
                    {{ user?.doc?.full_name }}
                  </span>
                  <span class="truncate font-mono text-p-sm text-ink-gray-6">
                    {{ userId }}
                  </span>
                </div>
              </div>
            </template>
          </FileUploader>
        </SettingsSection>
        <SettingsSection :title="__('Account and security')">
          <SettingRow
            v-if="hasAgentRecord"
            :label="__('Availability')"
            :description="
              __(
                'Set your availability so your team knows when you\'re reachable.'
              )
            "
          >
            <AvailabilityMenu />
          </SettingRow>
          <SettingRow
            :label="__('Emails and signature')"
            :description="
              __(
                'Manage your account emails and email signature for communication.'
              )
            "
          >
            <Button
              :label="__('Set up emails')"
              @click="emit('updateStep', 'user-email-settings')"
            >
              <template #suffix>
                <LucideChevronRight
                  class="size-4 rtl:rotate-180"
                  aria-hidden="true"
                />
              </template>
            </Button>
          </SettingRow>
          <SettingRow
            :label="__('Password')"
            :description="__('Change your account password for security.')"
          >
            <Button
              :label="__('Change password')"
              @click="showChangePasswordModal = true"
            >
              <template #prefix>
                <LucideLock class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </SettingRow>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
  <ChangePasswordModal
    v-if="showChangePasswordModal"
    v-model="showChangePasswordModal"
  />
</template>

<script setup lang="ts">
import {
  Avatar,
  Button,
  createDocumentResource,
  FileUploader,
  LoadingIndicator,
  toast,
} from "frappe-ui";
import { computed, ref } from "vue";

import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideLock from "~icons/lucide/lock";
import LucideX from "~icons/lucide/x";
const emit = defineEmits(["updateStep"]);

import AvailabilityMenu from "@/components/AvailabilityMenu.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { useAgentStatusStore } from "@/stores/agentStatus";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";
import ChangePasswordModal from "./components/ChangePasswordModal.vue";

const agentStatusStore = useAgentStatusStore();
const showChangePasswordModal = ref(false);

const { userId, hasAgentRecord } = useAuthStore();
const user = createDocumentResource({ doctype: "User", name: userId });

const isHoveringRemove = ref(false);

const profileTooltipText = computed(() => {
  if (isHoveringRemove.value) return __("Remove Photo");
  return user.doc?.user_image ? __("Change Photo") : __("Upload Photo");
});

const fullName = computed({
  get: () => user.doc?.full_name ?? "",
  set: (val) => {
    if (!user.doc) return;
    const [firstName, ...lastName] = val.split(" ");
    user.doc.first_name = firstName;
    user.doc.last_name = lastName.join(" ");
  },
});

function save() {
  user.save.submit(null, {
    onSuccess: () => {
      toast.success(__("Profile updated successfully."));
    },
    onError: (err: { message: string; messages: string[] }) => {
      toast.error(err.message + ": " + err.messages[0]);
    },
  });
}

function updateImage(fileUrl = "") {
  isHoveringRemove.value = false;
  user.doc.user_image = fileUrl;
  save();
}
</script>
