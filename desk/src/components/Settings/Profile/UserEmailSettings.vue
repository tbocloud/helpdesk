<template>
  <SettingsLayoutBase
    :title="__('Emails and signature')"
    :description="
      __('The signature under your replies, and the accounts you send from.')
    "
    :back-label="__('Back to profile')"
    :dirty="isDirty"
    :saving="user?.save?.loading"
    :loading="!user.doc"
    @back="goBack"
    @save="update"
  >
    <template #content>
      <div v-if="user.doc">
        <SettingsSection
          :title="__('Signature')"
          :description="__('Manage your email signature.')"
        >
          <CompactEditor
            v-model="user.doc.email_signature"
            :placeholder="__('Write your email signature here.')"
          />
        </SettingsSection>
        <SettingsSection
          :title="__('Emails')"
          :description="
            __(
              'Switch between outgoing email accounts when sending emails from your configured accounts.'
            )
          "
        >
          <div>
            <div
              v-if="user.doc.user_emails?.length"
              class="w-full border rounded-md mb-2 border-outline-elevation-2"
            >
              <div
                class="grid grid-cols-[4fr_4fr_0.3fr] gap-2 px-4 py-3 text-sm-medium text-ink-gray-5 border-b border-outline-elevation-2"
              >
                <span>{{ __("Email Account") }}</span>
                <span>{{ __("Email") }}</span>
                <span></span>
              </div>
              <div
                v-for="e in user.doc.user_emails"
                :key="e.name"
                class="grid grid-cols-[4fr_4fr_0.3fr] gap-2 group items-center px-4 py-2.5 text-base border-b border-outline-elevation-2 last:border-b-0"
              >
                <span class="min-w-0 truncate font-medium text-ink-gray-8">
                  {{ e.email_account }}
                </span>
                <span class="min-w-0 truncate text-ink-gray-6">{{
                  e.email_id
                }}</span>
                <div
                  class="transition-opacity sm:opacity-0 sm:focus-within:opacity-100 sm:group-hover:opacity-100"
                >
                  <Button
                    class="w-10"
                    variant="ghost"
                    :tooltip="__('Remove')"
                    :label="__('Remove {0}', e.email_id)"
                    @click.prevent="removeEmail(e)"
                  >
                    <template #icon>
                      <LucideX class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </div>
              </div>
            </div>
            <Autocomplete
              value=""
              :options="filteredEmails"
              @change="(e) => addEmail(e)"
            >
              <template #target="{ togglePopover }">
                <Button
                  variant="outline"
                  :label="__('Add email account')"
                  @click="togglePopover()"
                >
                  <template #prefix>
                    <LucidePlus class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </template>
              <template #item-label="{ option }">
                <div class="flex flex-col gap-1 text-ink-gray-9">
                  <div>{{ option.label }}</div>
                  <div class="text-ink-gray-4 text-sm">
                    {{ option.email }}
                  </div>
                </div>
              </template>
            </Autocomplete>
          </div>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
  <ConfirmDialog
    v-model="showConfirmDialog.show"
    :title="showConfirmDialog.title"
    :message="showConfirmDialog.message"
    :onConfirm="showConfirmDialog.onConfirm"
    :onCancel="
      () => {
        if (showConfirmDialog.onCancel) {
          showConfirmDialog.onCancel();
        } else {
          showConfirmDialog.show = false;
        }
      }
    "
  />
</template>
<script setup>
import CompactEditor from "@/components/CompactEditor.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import Autocomplete from "@/components/frappe-ui/Autocomplete.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { getUserEmailInfo } from "@/composables/useUserEmailInfo";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { normalize } from "@/utils";
import { Button, createDocumentResource, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideX from "~icons/lucide/x";
import SettingsSection from "../SettingsSection.vue";

const { userId } = useAuthStore();
const user = createDocumentResource({ doctype: "User", name: userId });
const emit = defineEmits(["updateStep"]);

const currentUserEmailInfo = getUserEmailInfo();

const filteredEmails = computed(() => {
  if (!currentUserEmailInfo.data?.available_emails) return [];
  const linkedEmails = user.doc.user_emails?.map((e) => e.email_id) || [];
  return currentUserEmailInfo.data.available_emails
    .map((doc) => ({
      label: doc.name,
      value: doc.name,
      email: doc.email_id,
    }))
    .filter((e) => !linkedEmails.includes(e.email));
});

const isSignatureDirty = computed(() => {
  return (
    normalize(currentUserEmailInfo.data?.email_signature) !==
    normalize(user?.doc?.email_signature)
  );
});

const isUserEmailListDirty = computed(() => {
  const emailIds = (list = []) => list.map((e) => e.email_id).sort();
  return (
    JSON.stringify(emailIds(currentUserEmailInfo.data?.outgoing_emails)) !==
    JSON.stringify(emailIds(user.doc.user_emails))
  );
});

const isDirty = computed(() => {
  return isSignatureDirty.value || isUserEmailListDirty.value;
});

function addEmail(email) {
  if (!user.doc.user_emails) user.doc.user_emails = [];
  user.doc.user_emails.push({
    email_account: email.label,
    email_id: email.email,
  });
}

function removeEmail(email) {
  user.doc.user_emails = user.doc.user_emails.filter(
    (e) => e.email_id !== email.email_id
  );
}

function update() {
  user.save.submit(null, {
    onSuccess: () => {
      toast.success(__("Email settings updated successfully."));
      currentUserEmailInfo.reload();
      user.reload();
    },
  });
}

const showConfirmDialog = ref({
  show: false,
  title: "",
  message: "",
  onConfirm: () => {},
});

const goBack = () => {
  const confirmDialogInfo = {
    show: true,
    title: __("Leave without saving?"),
    message: __(
      "Your changes on this page haven't been saved and will be lost."
    ),
    onConfirm: goBack,
  };
  if (isDirty.value && !showConfirmDialog.value.show) {
    showConfirmDialog.value = confirmDialogInfo;
    return;
  }

  showConfirmDialog.value.show = false;
  emit("updateStep", "profile");
};
</script>
