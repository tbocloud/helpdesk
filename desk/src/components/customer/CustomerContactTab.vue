<template>
  <div>
    <div class="flex items-center justify-between gap-3 pb-4">
      <h2 class="text-lg-semibold text-ink-gray-9">{{ __("Contacts") }}</h2>
      <div v-if="hasPermission()" class="flex flex-wrap items-center gap-2">
        <Button
          :label="__('Invite to portal')"
          variant="ghost"
          @click="showInviteContact = true"
        />
        <Button
          :label="__('Add contact')"
          variant="subtle"
          @click="showAddContact = true"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </div>
    <div
      v-if="customer.getContacts?.loading && !customer.getContacts?.data"
      class="grid grid-cols-1 gap-4 md:grid-cols-3"
      :aria-label="__('Loading')"
    >
      <div
        v-for="i in 3"
        :key="i"
        class="h-40 animate-pulse rounded-lg bg-surface-gray-2"
      />
    </div>
    <TaskyState
      v-else-if="customer.getContacts?.error && !customer.getContacts?.data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the contacts')"
      :message="errorText(customer.getContacts.error, __('Try again.'))"
      error
    >
      <Button :label="__('Retry')" @click="customer.getContacts.reload()" />
    </TaskyState>
    <TaskyState
      v-else-if="!customer.getContacts?.data?.length"
      :icon="LucideUserX"
      :title="__('No contacts yet')"
      :message="
        hasPermission()
          ? __(
              'Add the people you mail and who sign off for this customer. Invite them to the portal when they need to raise tickets.'
            )
          : __('Nobody has been added to this customer yet.')
      "
    >
      <Button
        v-if="hasPermission()"
        :label="__('Add contact')"
        @click="showAddContact = true"
      />
    </TaskyState>
    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <ContactCard
        v-for="contact in customer.getContacts?.data"
        :key="contact.contact_name"
        :contact="contact"
        @update="customer.getContacts?.reload()"
      />
    </div>
  </div>
  <AddContactDialog v-model="showAddContact" />
  <InviteContactDialog
    v-model="showInviteContact"
    :excluded-emails="existingContacts"
  />
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { CustomerResourceSymbol } from "@/types";
import TaskyState from "@/components/TaskyState.vue";
import { errorText, hasPermission } from "@/utils";
import { Button } from "frappe-ui";
import { computed, inject, onMounted, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePlus from "~icons/lucide/plus";
import LucideUserX from "~icons/lucide/user-x";
import { agents } from "../Settings/agents";
import AddContactDialog from "./AddContactDialog.vue";
import ContactCard from "./ContactCard.vue";
import InviteContactDialog from "./InviteContactDialog.vue";

const customer = inject(CustomerResourceSymbol)!;

const showAddContact = ref(false);
const showInviteContact = ref(false);

const existingContacts = computed(() => {
  if (agents.loading && customer.getContacts?.loading) return [];
  if (!agents.data && !customer.getContacts?.data) return [];

  return [
    ...new Set([
      ...(agents.data?.map((a) => a.user) || []),
      ...(customer.getContacts?.data?.map((c) => c.email_id) || []),
      "Guest",
    ]),
  ];
});

onMounted(() => {
  agents.fetch();
});
</script>
