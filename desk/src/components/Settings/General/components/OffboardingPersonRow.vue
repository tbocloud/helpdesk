<template>
  <SettingsListItem
    :title="person.full_name || person.user"
    :subtitle="person.user"
  >
    <template #badges>
      <TaskyBadge :label="__(person.reason)" />
    </template>
    <template v-if="person.disabled_on" #meta>
      <span class="shrink-0 font-mono text-sm tabular-nums text-ink-gray-6">
        {{ formatDate(person.disabled_on) }}
      </span>
    </template>
  </SettingsListItem>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import SettingsListItem from "../../SettingsListItem.vue";

/** One person offboarding found or disabled: name, email, reason and when. */
defineProps<{
  person: {
    user: string;
    full_name?: string;
    reason: string;
    disabled_on?: string;
  };
}>();

const formatDate = (value: string) => dayjs(value).format("D MMM YYYY, HH:mm");
</script>
