import { useAuthStore } from "@/stores/auth";
import { ListResource, Notification } from "@/types";
import { isCustomerPortal } from "@/utils";
import {
  canPlaySound,
  NEW_TICKET_TONE,
  playNotificationSound,
} from "@/composables/notificationSound";
import { router } from "@/router";
import { __ } from "@/translation";
import { createListResource, createResource, toast } from "frappe-ui";
import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { globalStore } from "./globalStore";

type NewNotification = {
  notification_type: string;
  message?: string;
  link?: string;
  /** a new ticket for the person who takes it: chimes when they turned it on */
  sound?: boolean;
};

// these carry their whole message; the panel builds the rest from the type
const TEXT_ONLY_TYPES = [
  "Reminder",
  "Task Completed",
  "New Ticket",
  "Ticket Update",
];

export function isTextOnly(n: Notification) {
  // a task assignment (no ticket) also carries its whole message and link
  return (
    TEXT_ONLY_TYPES.includes(n.notification_type) ||
    (n.notification_type === "Assignment" && !n.reference_ticket)
  );
}

export const useNotificationStore = defineStore("notification", () => {
  const authStore = useAuthStore();
  const { $socket } = globalStore();

  const visible = ref(false);
  const resource: ListResource<Notification> = createListResource({
    doctype: "HD Notification",
    cache: "Notifications",
    fields: [
      "creation",
      "message",
      "name",
      "notification_type",
      "read",
      "reference_comment",
      "reference_ticket",
      "reference_doctype",
      "reference_name",
      "link",
      "user_from",
      "user_to",
    ],
    orderBy: "modified desc",
  });
  const clear = createResource({
    url: "helpdesk.helpdesk.doctype.hd_notification.utils.clear",
    auto: false,
    onSuccess: () => resource.reload(),
  });

  const read = (n: Notification) => {
    createResource({
      url: "helpdesk.helpdesk.doctype.hd_notification.utils.clear",
      auto: true,
      // without a ticket the server would mark every notification read
      params: n.reference_ticket
        ? { ticket: n.reference_ticket }
        : { notification: n.name },
      onSuccess: () => resource.reload(),
    });
  };

  const data = computed(() => resource.data || []);
  const unread = computed(() => data.value.filter((d) => !d.read).length);

  function toggle() {
    visible.value = !visible.value;
  }

  watch(
    () => authStore.hasDeskAccess,
    (newVal) => {
      if (!newVal) return;
      resource.filters = {
        user_to: ["=", authStore.userId],
      };
      resource.reload();
    },
    { immediate: true }
  );
  $socket.on("helpdesk:comment-reaction-update", () => {
    if (isCustomerPortal.value) return;
    resource.reload();
  });
  // sent only to the recipient, the moment a notification is created
  $socket.on("helpdesk:new-notification", (n: NewNotification) => {
    if (isCustomerPortal.value) return;
    resource.reload();
    if (n.notification_type === "Task Completed") {
      playNotificationSound();
      if (n.message) toast.success(n.message);
    } else if (n.notification_type === "New Ticket") {
      announceNewTicket(n);
    }
  });

  // always a toast; the tone only for the person taking the ticket, when they
  // turned it on and the browser allows sound (docs/ticket-owners.md)
  function announceNewTicket(n: NewNotification) {
    if (n.sound && authStore.newTicketSound && canPlaySound()) {
      playNotificationSound(NEW_TICKET_TONE);
    }
    const [title, ...rest] = (n.message || __("New ticket")).split("\n");
    toast(title, {
      description: rest.join(" · ") || undefined,
      action: n.link
        ? { label: __("Open"), onClick: () => router.push(n.link) }
        : undefined,
    });
  }

  return {
    clear,
    data,
    toggle,
    read,
    unread,
    visible,
    resource,
  };
});
