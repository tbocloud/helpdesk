<template>
  <div>
    <div class="flex items-center gap-3">
      <Avatar :label="displayName" :image="contactImage" size="2xl" />
      <div class="min-w-0 flex-1">
        <Tooltip :text="displayName">
          <p class="truncate text-base font-semibold text-ink-gray-9">
            {{ displayName }}
          </p>
        </Tooltip>
        <p
          v-if="contact.data?.email_id && contact.data?.name"
          class="truncate text-xs text-ink-gray-5"
        >
          {{ contact.data.email_id }}
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-0.5">
        <template v-if="isCallingEnabled">
          <Tooltip :text="contact.data?.email_id">
            <Button
              variant="ghost"
              size="sm"
              :aria-label="__('Reply by email')"
              @click="toggleEmailBox()"
            >
              <template #icon>
                <EmailIcon class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </Tooltip>
          <Tooltip :text="__('Call contact')">
            <Button
              variant="ghost"
              size="sm"
              :aria-label="__('Call contact')"
              @click="callContact"
            >
              <template #icon>
                <PhoneIcon class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </Tooltip>
        </template>
        <Tooltip
          v-if="!contact.loading && contact.data?.name"
          :text="__('Open contact')"
        >
          <Button
            variant="ghost"
            size="sm"
            :aria-label="__('Open contact')"
            @click="openContact(contact.data.name)"
          >
            <template #icon>
              <LucideExternalLink class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Tooltip>
      </div>
    </div>

    <!-- the customer is set in Details and named in the header -->
    <dl class="mt-3">
      <div class="flex items-center justify-between gap-3 text-sm leading-6">
        <dt class="text-ink-gray-6">{{ __("Their open tickets") }}</dt>
        <dd class="font-mono tabular-nums text-ink-gray-9">
          {{ openTicketCount }}
        </dd>
      </div>
    </dl>

    <SetContactPhoneModal
      v-model="showPhoneModal"
      :name="contact.data?.name ?? ''"
      @onUpdate="contact.reload"
    />
  </div>
</template>

<script setup lang="ts">
import { toggleEmailBox } from "@/pages/ticket/modalStates";
import { useTelephonyStore } from "@/stores/telephony";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { TicketContactSymbol, TicketSymbol } from "@/types";
import { openContact } from "@/utils";
import { Avatar, Button, Tooltip, createResource } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, inject, ref, watch } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import EmailIcon from "../icons/EmailIcon.vue";
import PhoneIcon from "../icons/PhoneIcon.vue";
import SetContactPhoneModal from "../ticket/SetContactPhoneModal.vue";
const telephonyStore = useTelephonyStore();
const { getUser } = useUserStore();
const { isCallingEnabled } = storeToRefs(telephonyStore);
const showPhoneModal = ref(false);

const ticket = inject(TicketSymbol)!;

const contact = inject(TicketContactSymbol)!;
const displayName = computed(
  () =>
    contact.value?.data?.name ||
    contact.value?.data?.email_id ||
    ticket.value?.doc?.raised_by ||
    ""
);
const contactImage = computed(() => {
  if (!contact.value?.data) return "";
  const email = contact.value?.data?.email_id ?? "";
  return (
    contact.value?.data?.image || (email && getUser(email)?.user_image) || ""
  );
});

// Unresolved tickets from the same contact (or sender when no contact is linked)
const openTickets = createResource({
  url: "frappe.client.get_count",
});

const openTicketsFilter = computed(() => {
  const doc = ticket.value?.doc;
  if (!doc) return null;
  const filter: Record<string, unknown> = {
    status_category: ["!=", "Resolved"],
  };
  if (doc.contact) filter.contact = doc.contact;
  else if (doc.raised_by) filter.raised_by = doc.raised_by;
  else return null;
  return filter;
});

watch(
  () => JSON.stringify(openTicketsFilter.value),
  () => {
    if (!openTicketsFilter.value) return;
    openTickets.submit({
      doctype: "HD Ticket",
      filters: openTicketsFilter.value,
    });
  },
  { immediate: true }
);

const openTicketCount = computed(() =>
  typeof openTickets.data === "number" ? openTickets.data : "—"
);

const callContact = () => {
  if (!contact.value.data.mobile_no && !contact.value.data.phone) {
    showPhoneModal.value = true;
    return;
  }
  telephonyStore.makeCall({
    number: contact.value.data.mobile_no || contact.value.data.phone,
    doctype: "HD Ticket",
    docname: ticket.value.name,
  });
};
</script>
