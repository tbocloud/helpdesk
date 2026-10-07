<template>
  <SettingsLayoutBase
    :title="__('Email Accounts')"
    :description="
      __(
        'The mailboxes tickets come in from and replies go out of, and which one is the default.'
      )
    "
  >
    <template #header-actions>
      <Button
        variant="solid"
        :label="__('Add email account')"
        @click="emit('update:step', 'email-add')"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #content>
      <SettingsList
        :items="emailAccounts.data"
        :label="__('Email accounts')"
        :loading="emailAccounts.list.loading"
        :error="emailAccounts.list.error"
        :has-more="emailAccounts.hasNextPage"
        :empty-icon="EmailIcon"
        :empty-title="__('No email accounts yet')"
        :empty-message="__('Connect a mailbox so emails to it become tickets.')"
        @retry="emailAccounts.reload()"
        @more="emailAccounts.next()"
      >
        <template #default="{ item: emailAccount }">
          <SettingsListItem
            :title="emailAccount.email_account_name"
            :subtitle="emailAccount.email_id"
            @open="emit('update:step', 'email-edit', emailAccount)"
          >
            <template #prefix>
              <EmailProviderIcon :logo="emailIcon[emailAccount.service]" />
            </template>
            <template #meta>
              <TaskyBadge
                :label="accountRole(emailAccount).label"
                :tone="accountRole(emailAccount).enabled ? 'info' : 'neutral'"
              />
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { EmailAccount } from "@/types";
import { Button, createListResource } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import { EmailIcon } from "../icons";
import { emailIcon } from "./emailConfig";
import EmailProviderIcon from "./EmailProviderIcon.vue";
import SettingsList from "./SettingsList.vue";
import SettingsListItem from "./SettingsListItem.vue";

const emit = defineEmits(["update:step"]);

const emailAccounts = createListResource({
  doctype: "Email Account",
  cache: ["Email Accounts"],
  fields: ["*"],
  filters: {
    email_id: ["Not Like", "%example%"],
  },
  pageLength: 10,
  auto: true,
  onSuccess: (accounts: EmailAccount[]) => {
    // convert 0 to false to handle boolean fields
    accounts.forEach((account) => {
      account.enable_incoming = Boolean(account.enable_incoming);
      account.enable_outgoing = Boolean(account.enable_outgoing);
      account.default_incoming = Boolean(account.default_incoming);
      account.default_outgoing = Boolean(account.default_outgoing);
    });
  },
});

/** What the account is used for; `enabled` is false when that direction is switched off. */
function accountRole(account: EmailAccount) {
  if (account.default_incoming && account.default_outgoing) {
    return {
      label: __("Default Sending and Inbox"),
      enabled: account.enable_incoming && account.enable_outgoing,
    };
  }
  if (account.default_incoming) {
    return { label: __("Default Inbox"), enabled: account.enable_incoming };
  }
  if (account.default_outgoing) {
    return { label: __("Default Sending"), enabled: account.enable_outgoing };
  }
  return { label: __("Inbox"), enabled: account.enable_incoming };
}
</script>
