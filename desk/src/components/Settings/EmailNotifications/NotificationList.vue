<template>
  <SettingsLayoutBase
    :title="__('Email Notifications')"
    :description="
      __(
        'The emails helpdesk sends to contacts and agents, and what each one says.'
      )
    "
  >
    <template #content>
      <SettingsList
        :items="notifications"
        :label="__('Email notifications')"
        :empty-icon="LucideMailOpen"
        :empty-title="__('No email notifications')"
      >
        <template #default="{ item: notification }">
          <SettingsListItem
            :title="__(notification.label)"
            :subtitle="__(notification.description)"
            @open="props.onSelect(notification)"
          />
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import type { AtLeastOneNotifcation, Notification } from "./types";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import LucideMailOpen from "~icons/lucide/mail-open";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";

const props = defineProps<{
  onSelect: (notification: Notification) => void;
}>();

const notifications: AtLeastOneNotifcation = [
  {
    name: "share_feedback",
    label: __("Share feedback"),
    description: __(
      "Sent to the user who has raised the ticket after the ticket is closed or resolved."
    ),
  },
  {
    name: "acknowledgement",
    label: __("Acknowledgement"),
    description: __("Sent to the user right after creating an email ticket."),
  },
  {
    name: "reply_to_agents",
    label: __("Reply from contact"),
    description: __(
      "Sent to all of the agents assigned to the ticket whenever a contact has replied."
    ),
  },
  {
    name: "reply_via_agent",
    label: __("Reply from agent"),
    description: __(
      "Sent to all of the recipients associated with the ticket whenever an agent has replied."
    ),
  },
];
</script>
