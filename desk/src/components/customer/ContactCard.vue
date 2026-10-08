<template>
  <!-- the whole card opens the contact; the menu sits above that link -->
  <div
    class="relative flex flex-col gap-2.5 rounded-lg border border-outline-gray-2 bg-surface-base px-3 py-2.5 transition-colors hover:border-outline-gray-4"
  >
    <div class="flex items-center justify-between gap-2">
      <div class="flex min-w-0 items-center gap-2">
        <Avatar
          size="lg"
          shape="circle"
          :image="contact.image ?? ''"
          :label="contact.contact_name"
        />
        <RouterLink
          :to="{ name: 'Contact', params: { id: contact.contact_name } }"
          class="min-w-0 truncate rounded text-sm text-ink-gray-9 after:absolute after:inset-0 after:rounded-lg focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-outline-gray-4"
        >
          {{ contact.contact_name }}
        </RouterLink>
      </div>
      <Dropdown
        v-if="hasPermission()"
        placement="right"
        :options="dropdownOptions"
      >
        <Button
          class="relative z-[1] shrink-0"
          variant="ghost"
          size="sm"
          :aria-label="__('Actions for {0}', contact.contact_name)"
        >
          <template #icon>
            <LucideEllipsis class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </Dropdown>
    </div>
    <div
      v-if="contact.is_primary || contact.is_manager"
      class="flex flex-wrap gap-1.5"
    >
      <TaskyBadge
        v-if="contact.is_primary"
        :label="__('Primary')"
        :icon="LucideStar"
        :title="__('The customer\'s main point of contact')"
      />
      <TaskyBadge
        v-if="contact.is_manager"
        :label="__('Manager')"
        :icon="LucideShieldCheck"
        :title="__('Can view tickets raised by all contacts of the customer.')"
      />
    </div>
    <dl class="flex flex-col gap-2 border-t border-outline-gray-2 pt-2.5">
      <div
        v-for="item in contactDetails"
        :key="item.label"
        class="flex min-w-0 items-center gap-2 text-sm"
      >
        <dt class="shrink-0">
          <component
            :is="item.icon"
            class="size-4 text-ink-gray-5"
            aria-hidden="true"
          />
          <span class="sr-only">{{ item.label }}</span>
        </dt>
        <dd
          class="min-w-0 truncate"
          :class="item.muted ? 'text-ink-gray-5' : 'text-ink-gray-8'"
        >
          {{ item.value }}
        </dd>
      </div>
    </dl>
  </div>
</template>

<script setup lang="ts">
import { globalStore } from "@/stores/globalStore";
import { __ } from "@/translation";
import { CustomerContact, CustomerResourceSymbol } from "@/types";
import { HDCustomerMember } from "@/types/doctypes";
import { getErrorMessage, hasPermission } from "@/utils";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { Avatar, Button, Dropdown, dayjs, toast } from "frappe-ui";
import { computed, inject, markRaw } from "vue";
import { RouterLink } from "vue-router";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideMail from "~icons/lucide/mail";
import LucidePhone from "~icons/lucide/phone";
import LucideShieldCheck from "~icons/lucide/shield-check";
import LucideStar from "~icons/lucide/star";
import LucideTicket from "~icons/lucide/ticket";
import ModifiedIcon from "../icons/ModifiedIcon.vue";

const props = defineProps<{
  contact: CustomerContact;
}>();
const emit = defineEmits(["update"]);

const { $dialog } = globalStore();
const customer = inject(CustomerResourceSymbol)!;

const ticketCountLabel = computed(() => {
  const count = props.contact.ticket_count;
  if (count === 0) return __("No open tickets");
  return count === 1
    ? __("1 open ticket")
    : __("{0} open tickets", String(count));
});

const contactDetails = computed(() => [
  {
    label: __("Email"),
    icon: markRaw(LucideMail),
    value: props.contact.email_id || __("No email"),
    muted: !props.contact.email_id,
  },
  {
    label: __("Phone"),
    icon: markRaw(LucidePhone),
    value: props.contact.mobile_no || __("No phone"),
    muted: !props.contact.mobile_no,
  },
  {
    label: __("Last seen"),
    icon: markRaw(ModifiedIcon),
    value: props.contact.last_active
      ? __("Last seen {0}", dayjs(props.contact.last_active).fromNow())
      : __("Never signed in"),
    muted: !props.contact.last_active,
  },
  {
    label: __("Open tickets"),
    icon: markRaw(LucideTicket),
    value: ticketCountLabel.value,
    muted: !props.contact.ticket_count,
  },
]);

const dropdownOptions = computed(() => {
  const primaryActions = [];
  if (!props.contact.is_primary) {
    primaryActions.push({
      label: __("Set as Primary"),
      icon: "star",
      onClick: () => {
        updatePrimaryContact();
      },
    });
  }
  const roleActions = [
    {
      label: __("Role"),
      icon: "briefcase",
      submenu: [
        {
          label: __("Customer"),
          icon: props.contact.is_manager ? undefined : "check",
          onClick: () => {
            if (!props.contact.is_manager) return;
            updateManagerRole(0);
          },
        },
        {
          label: __("Customer Manager"),
          icon: props.contact.is_manager ? "check" : undefined,
          onClick: () => {
            if (props.contact.is_manager) return;
            updateManagerRole(1);
          },
        },
      ],
    },
  ];

  const destructiveActions = [
    {
      label: __("Remove Contact"),
      icon: "x",
      theme: "red" as const,
      onClick: () => {
        removeContact();
      },
    },
  ];
  const deleteActionGroup = {
    group: "",
    hideLabel: true,
    items: destructiveActions,
  };

  if (props.contact.is_primary) {
    return [deleteActionGroup];
  }

  return [
    {
      group: "",
      hideLabel: true,
      items: [...primaryActions, ...roleActions],
    },
    deleteActionGroup,
  ];
});

function updateManagerRole(isManager: 0 | 1) {
  const title = isManager
    ? __("Grant Manager Access")
    : __("Revoke Manager Access");
  const message = isManager
    ? __(
        "They'll get access to tickets raised by everyone in the organisation."
      )
    : __("They'll only see their own tickets going forward.");

  $dialog({
    title,
    message,
    actions: [
      {
        label: isManager ? __("Make manager") : __("Remove manager access"),
        variant: "solid",
        onClick: ({ close }: { close: () => void }) => {
          const contact = customer.doc.contacts?.find(
            (c) => c.contact_name === props.contact.contact_name
          ) as HDCustomerMember | undefined;
          if (!contact) return;

          contact.is_manager = isManager;
          customer.setValue.submit(
            { contacts: customer.doc.contacts },
            {
              onSuccess() {
                emit("update");
                close();
                toast.success(__("Role updated successfully"));
              },
              onError(error: any) {
                getErrorMessage(error, true);
              },
            }
          );
        },
      },
    ],
  });
}

function updatePrimaryContact() {
  if (customer.doc.primary_contact === props.contact.contact_name) return;

  $dialog({
    title: __("Set Primary Contact"),
    message: __(
      "This contact will become the primary point of contact and will be able to view tickets raised by all other contacts in the organisation."
    ),
    actions: [
      {
        label: __("Set as primary"),
        variant: "solid",
        onClick: ({ close }: { close: () => void }) =>
          customer.setValue.submit(
            { primary_contact: props.contact.contact_name },
            {
              onSuccess() {
                emit("update");
                close();
                toast.success(__("Primary contact updated"));
              },
              onError(error: any) {
                getErrorMessage(error, true);
              },
            }
          ),
      },
    ],
  });
}

function removeContact() {
  $dialog({
    title: __("Remove Contact"),
    message: __(
      "Are you sure you want to remove this contact from the customer?"
    ),
    actions: [
      {
        label: __("Remove contact"),
        variant: "solid",
        theme: "red",
        onClick: ({ close }: { close: () => void }) => {
          return customer.setValue.submit(
            {
              contacts: customer.doc.contacts?.filter(
                (c) => c.contact_name !== props.contact.contact_name
              ),
            },
            {
              onSuccess() {
                emit("update");
                close();
                toast.success(__("Contact removed successfully"));
              },
              onError(error: any) {
                getErrorMessage(error, true);
              },
            }
          );
        },
      },
    ],
  });
}
</script>
