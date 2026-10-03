<template>
  <span
    v-if="notificationStore.visible"
    ref="target"
    class="fixed z-10 h-screen overflow-auto bg-surface-base"
    :style="{
      'box-shadow': '8px 0px 8px rgba(0, 0, 0, 0.1)',
      'max-width': '350px',
      'min-width': '350px',
      left: sidebarStore.width,
    }"
  >
    <div
      class="sticky top-0 z-10 flex items-center justify-between border-b bg-surface-base px-5 py-2.5"
    >
      <span class="text-lg-medium">Notifications</span>
      <div>
        <Button
          theme="blue"
          variant="ghost"
          @click="() => notificationStore.clear.submit()"
          v-if="notificationStore.data.length"
        >
          <template #icon>
            <LucideCheckCheck class="h-4 w-4" />
          </template>
        </Button>
        <Button
          theme="gray"
          variant="ghost"
          @click="() => notificationStore.toggle()"
        >
          <template #icon>
            <LucideX class="h-4 w-4" />
          </template>
        </Button>
      </div>
    </div>
    <div class="divide-y text-base" v-if="notificationStore.data.length">
      <component
        :is="isOutside(n) ? 'a' : RouterLink"
        v-for="n in notificationStore.data"
        :key="n.name"
        class="flex cursor-pointer items-start gap-3.5 px-5 py-2.5 hover:bg-surface-gray-2"
        v-bind="linkProps(n)"
        @click="
          () => {
            handleNotificationClick(n);
          }
        "
      >
        <span
          v-if="n.notification_type === 'Reminder'"
          class="grid size-8 shrink-0 place-items-center rounded-full bg-warning-soft text-warning"
          aria-hidden="true"
        >
          <LucideAlarmClock class="size-4" />
        </span>
        <UserAvatar v-else :name="n.user_from" />
        <span>
          <div
            v-if="n.notification_type === 'Reminder'"
            class="mb-2 whitespace-pre-line leading-5 text-ink-gray-8"
          >
            {{ n.message }}
          </div>
          <div v-else class="mb-2 leading-5">
            <span class="space-x-1 text-ink-gray-7">
              <span
                class="font-medium text-ink-gray-9"
                v-if="n.notification_type !== 'Reaction' || !n.message"
              >
                {{ n.user_from }}
              </span>
              <span v-if="n.notification_type === 'Mention'"
                >mentioned you in ticket</span
              >
              <span v-if="n.notification_type === 'Assignment'"
                >assigned you a ticket</span
              >
              <span v-if="n.notification_type === 'Reaction'">
                {{ n.message || "has reopened the ticket" }}
              </span>
            </span>
            <span class="font-medium text-ink-gray-9"
              >&nbsp{{ n.reference_ticket }}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <div class="text-sm text-ink-gray-5">
              {{ dayjs.tz(n.creation).fromNow() }}
            </div>
            <div
              v-if="!n.read"
              class="h-1.5 w-1.5 rounded-full bg-surface-blue-5"
            />
          </div>
        </span>
      </component>
    </div>
    <div
      class="p-5 text-center text-ink-gray-4 flex flex-col items-center justify-center gap-2 mt-20"
      v-else
    >
      <LucideBell class="size-6" />
      <p class="text-base text-ink-gray-8">You are all caught up!</p>
    </div>
  </span>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";
import { UserAvatar } from "@/components";
import { dayjs } from "frappe-ui";
import { useNotificationStore } from "@/stores/notification";
import { useSidebarStore } from "@/stores/sidebar";
import { Notification } from "@/types";
import { onClickOutside } from "@vueuse/core";
import { ref } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";

const notificationStore = useNotificationStore();
const sidebarStore = useSidebarStore();
const target = ref(null);
onClickOutside(
  target,
  () => {
    if (notificationStore.visible) {
      notificationStore.toggle();
    }
  },
  {
    ignore: ["#notifications-btn"],
  }
);

function handleNotificationClick(n: Notification) {
  notificationStore.toggle();
  if (n.read) return;
  notificationStore.read(n);
}

// a reminder can point outside TBO Support, e.g. a pull request on GitHub
function isOutside(n: Notification) {
  return typeof n.link === "string" && n.link.startsWith("https://");
}

function linkProps(n: Notification) {
  return isOutside(n)
    ? { href: n.link, target: "_blank", rel: "noopener noreferrer" }
    : { to: getRoute(n) };
}

function getRoute(n: Notification) {
  switch (n.notification_type) {
    case "Reminder":
      return n.link || { name: "MyWork" };
    case "Mention":
      return {
        name: "TicketAgent",
        params: {
          ticketId: n.reference_ticket,
        },
        hash: "#comment-" + n.reference_comment,
      };
    case "Assignment":
      return {
        name: "TicketAgent",
        params: {
          ticketId: n.reference_ticket,
        },
      };
    case "Reaction":
      return {
        name: "TicketAgent",
        params: {
          ticketId: n.reference_ticket,
        },
        hash: n.reference_comment
          ? "#comment-" + n.reference_comment
          : undefined,
      };
  }
}
</script>
