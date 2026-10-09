<template>
  <div
    class="flex h-full flex-col overflow-y-hidden max-w-screen-xl mx-auto w-full"
  >
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" class="-ml-[2px]" />
      </template>
    </LayoutHeader>
    <TaskyState
      v-if="contact.get.error && !contact.doc"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t open this contact')"
      :message="
        errorText(
          contact.get.error,
          __('It may have been deleted, or you may not have access.')
        )
      "
      error
    >
      <Button :label="__('Retry')" @click="contact.reload()" />
      <Button
        :label="__('All contacts')"
        @click="router.push({ name: 'ContactList' })"
      />
    </TaskyState>
    <div
      v-else-if="!contact.doc"
      class="flex items-center gap-3 px-5 pt-5"
      :aria-label="__('Loading')"
    >
      <span class="size-[52px] animate-pulse rounded-full bg-surface-gray-2" />
      <div class="flex flex-col gap-2">
        <span class="h-5 w-48 animate-pulse rounded bg-surface-gray-2" />
        <span class="h-3.5 w-64 animate-pulse rounded bg-surface-gray-2" />
      </div>
    </div>
    <div v-else class="flex min-h-0 flex-1 flex-col gap-4">
      <!-- ContactInfo -->
      <PageInfo
        :avatar="{
          label: `${contact.doc.full_name}`.trim(),
          image: contact.doc.image ?? undefined,
          shape: 'circle',
        }"
        :doc-info="contactInfo"
        :badge="invitationBadge"
      >
        <template #actions>
          <template v-if="hasPermission()">
            <Button variant="subtle" @click="showEditDialog = true">
              <template #prefix>
                <LucideSquarePen class="size-4" aria-hidden="true" />
              </template>
              {{ __("Edit") }}
            </Button>
            <Dropdown :options="dropdownActions" placement="right">
              <Button variant="subtle" :aria-label="__('More actions')">
                <template #icon>
                  <LucideEllipsis class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </Dropdown>
          </template>
        </template>
      </PageInfo>
      <div class="flex flex-1 flex-col overflow-y-auto overscroll-y-contain">
        <TicketStats dt="Contact" :dn="id" />
        <Tabs
          v-model="activeTab"
          :tabs="tabs"
          class="tabs-sticky-header [&_[role='tablist']]:!bg-surface-base"
        >
          <template #tab-item="{ tab, selected }: any">
            <button
              class="flex shrink-0 items-center gap-2 whitespace-nowrap border-b border-transparent py-2 text-base transition-colors hover:text-ink-gray-9"
              :class="selected ? 'text-ink-gray-9' : 'text-ink-gray-5'"
            >
              <component
                :is="tab.icon"
                v-if="tab.icon"
                class="size-4"
                aria-hidden="true"
              />
              {{ tab.label }}
              <span
                class="rounded px-1 font-mono text-xs tabular-nums"
                :class="
                  selected
                    ? 'bg-surface-gray-3 text-ink-gray-8'
                    : 'text-ink-gray-5'
                "
              >
                {{ tab.count }}
              </span>
            </button>
          </template>
          <template #tab-panel="{ tab }">
            <div class="flex min-h-0 flex-1 flex-col p-5">
              <TicketsTab
                v-if="tab.hash === 'tickets'"
                :ticketsListResource="ticketsListResource"
                :ticketsCountResource="ticketsCountResource"
                :baseFilter="{ contact: props.id }"
                :additionalFilter="
                (contactInfoResource.data?.customers?.length ?? 0) > 1
                  ? {
                      key: 'customer',
                      placeholder: __('Customer'),
                      doctype: 'HD Customer',
                      filters: {
                        name: ['in', contactInfoResource.data.customers.map((c: { name: string }) => c.name)],
                      },
                    }
                  : undefined
              "
              />
              <ContactFeedback
                v-else-if="tab.hash === 'feedback'"
                :name="props.id"
              />
            </div>
          </template>
        </Tabs>
      </div>
    </div>
    <DeleteWithTicketsDialog
      v-model="showDeleteDialog"
      :name="id"
      link-field="contact"
      :message="
        __(
          'Are you sure you want to delete this contact? The contact will be permanently deleted and unlinked from any associated customers and tickets.'
        )
      "
      :on-delete="handleDelete"
    />
    <EditContactDialog
      v-if="showEditDialog"
      v-model="showEditDialog"
      :name="id"
    />
  </div>
</template>

<script setup lang="ts">
import ContactCustomers from "@/components/contact/ContactCustomers.vue";
import ContactFeedback from "@/components/contact/ContactFeedback.vue";
import TicketsTab from "@/components/customer/TicketsTab.vue";
import DeleteWithTicketsDialog from "@/components/DeleteWithTicketsDialog.vue";
import ModifiedIcon from "@/components/icons/ModifiedIcon.vue";
import TicketFeedbackIcon from "@/components/icons/TicketFeedbackIcon.vue";
import TicketHashIcon from "@/components/icons/TicketHashIcon.vue";
//@ts-ignore
import EditContactDialog from "@/components/contact/EditContactDialog.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import PageInfo from "@/components/PageInfo.vue";
import TaskyState from "@/components/TaskyState.vue";
import {
  PORTAL_BADGE,
  useContact,
  useContactFeedback,
  useContactInvite,
  useContactResetPassword,
} from "@/composables/contact";
import { __ } from "@/translation";
import { errorText, hasPermission } from "@/utils";
import {
  Breadcrumbs,
  Button,
  Dropdown,
  Tabs,
  dayjs,
  usePageMeta,
} from "frappe-ui";
import { computed, h, markRaw, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideMail from "~icons/lucide/mail";
import LucideMapPin from "~icons/lucide/map-pin";
import LucidePhone from "~icons/lucide/phone";
import LucideSquarePen from "~icons/lucide/square-pen";
import LucideTrash2 from "~icons/lucide/trash-2";
import { getTicketListResource } from "../../stores/docTickets";

const props = defineProps<{
  id: string;
}>();

const route = useRoute();
const router = useRouter();

const {
  doc: contact,
  contactInfoResource,
  handleDelete,
} = useContact(props.id);

const { feedbackCount } = useContactFeedback(props.id);

const { ticketsListResource, ticketsCountResource } = getTicketListResource();

const tabs = computed(() => [
  {
    label: __("Tickets"),
    hash: "tickets",
    count: ticketsCountResource.data ?? 0,
    icon: h(TicketHashIcon, { class: "size-4" }),
  },
  {
    label: __("Feedback"),
    hash: "feedback",
    count: feedbackCount.data ?? 0,
    icon: h(TicketFeedbackIcon, { class: "size-4" }),
  },
]);

const activeTab = computed<number>({
  get() {
    const index = tabs.value.findIndex((t) => t.hash === route.hash.slice(1));
    return index === -1 ? 0 : index;
  },
  set(i) {
    router.replace({ hash: i === 0 ? "" : `#${tabs.value[i].hash}` });
  },
});

const contactInfo = computed(() => {
  if (
    contactInfoResource.loading ||
    !contactInfoResource.data ||
    !contact.doc?.name
  ) {
    return [];
  }
  const info = [
    {
      icon: markRaw(LucideMail),
      value: contact.doc?.email_id,
      condition: !!contact.doc?.email_id,
    },
    {
      icon: markRaw(LucidePhone),
      value: contact.doc?.mobile_no,
      condition: !!contact.doc?.mobile_no,
    },
    {
      icon: markRaw(LucideMapPin),
      value: contactInfoResource.data?.country,
      condition: !!contactInfoResource.data?.country,
    },
    {
      icon: markRaw(ModifiedIcon),
      value: __("Last seen {0}", [
        dayjs(contactInfoResource.data?.last_seen).fromNow(),
      ]),
      condition: !!contactInfoResource.data?.last_seen,
    },
    {
      component: markRaw(
        h(ContactCustomers, {
          customers: contactInfoResource.data?.customers ?? [],
        })
      ),
      condition: (contactInfoResource.data?.customers?.length ?? 0) > 0,
    },
  ];
  return info;
});

const { resendInvite, inviteAsUser } = useContactInvite();
const { resetPassword } = useContactResetPassword(() => contact.doc?.user);

const showEditDialog = ref(false);

const invitation = computed(() => contactInfoResource.data?.invitation);

const invitationBadge = computed(() => {
  const inv = invitation.value;
  if (!inv?.name) return null;
  if (inv.status === "Expired") {
    return {
      ...PORTAL_BADGE.expired,
      tooltip: __("Invitation expired. Resend to invite again."),
    };
  }
  return {
    ...PORTAL_BADGE.invited,
    tooltip: __("Invite sent. Waiting for the user to accept."),
  };
});

const showDeleteDialog = ref(false);

const dropdownActions = computed(() => {
  const baseActions = [];
  if (!contact.doc?.user && !invitation.value?.name) {
    baseActions.push({
      label: __("Invite as User"),
      icon: "user-plus",
      onClick: async () => {
        await inviteAsUser(props.id, contact.doc?.email_id);
        contactInfoResource.reload();
      },
    });
  }
  if (invitation.value?.name) {
    baseActions.push({
      label: __("Resend Invite"),
      icon: "mail",
      onClick: async () => {
        await resendInvite(
          invitation.value!.name,
          invitation.value!.status,
          props.id,
          contact.doc?.email_id
        );
        contactInfoResource.reload();
      },
    });
  }
  if (contact.doc?.user) {
    baseActions.push({
      label: __("Send reset password email"),
      icon: "mail",
      onClick: () => {
        resetPassword();
      },
    });
  }
  return [
    {
      group: __("Actions"),
      hideLabel: true,
      items: baseActions,
    },
    {
      group: __("Danger"),
      hideLabel: true,
      items: [
        {
          label: __("Delete"),
          icon: LucideTrash2,
          theme: "red",
          onClick: () => {
            showDeleteDialog.value = true;
          },
        },
      ],
    },
  ];
});

const breadcrumbs = [
  {
    label: __("Contacts"),
    route: { name: "ContactList" },
  },
  {
    label: props.id,
  },
];

onMounted(() => {
  ticketsListResource.update({
    filters: {
      contact: props.id,
    },
  });
  ticketsListResource.fetch();
  ticketsCountResource.fetch();
});

usePageMeta(() => ({ title: __("Contact: {0}", props.id) }));
</script>

<style scoped>
/* frappe-ui's TabsRoot clips with overflow-hidden, which traps the sticky
   tablist. Let it overflow so the tablist sticks to the page scroll container. */
.tabs-sticky-header {
  overflow: visible !important;
}
/* Same for the tab panels, so sticky children (e.g. the ticket filter bar)
   can stick to the page scroll container instead of being clipped. */
.tabs-sticky-header :deep([role="tabpanel"]) {
  overflow: visible !important;
}
.tabs-sticky-header :deep([role="tablist"]) {
  position: sticky;
  top: 0;
  z-index: 10;
}
</style>
