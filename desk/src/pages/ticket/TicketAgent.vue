<template>
  <div v-if="ticket.doc?.name" class="flex-1">
    <TicketHeader
      :viewers="viewers"
      :details-open="detailsOpen"
      @toggle-details="detailsOpen = !detailsOpen"
    />
    <div class="h-full flex overflow-hidden">
      <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
        <!-- Tabs & Communication Area -->
        <TicketActivityPanel />
      </div>

      <!-- Side panel: inline with a resizer from lg, a sheet below -->
      <TicketSidebar v-model:open="detailsOpen" :sheet="isSheet" />
    </div>
    <SetContactPhoneModal
      v-if="ticket.doc.contact"
      v-model="showPhoneModal"
      :name="ticket.doc?.contact"
      @onUpdate="ticket.reload"
    />
  </div>
  <div
    v-else-if="!ticket.doc && !ticket.get?.error"
    class="grid h-full place-items-center"
  >
    <LoadingIndicator class="w-6 text-ink-gray-4" />
  </div>

  <div v-else class="grid h-full place-items-center">
    <TaskyState
      :icon="TicketIcon"
      :title="__('Ticket not found')"
      :message="
        __('You don\'t have access to this ticket, or it no longer exists.')
      "
    >
      <Button :route="{ name: 'TicketsAgent' }" variant="subtle">
        <template #prefix>
          <LucideArrowLeft class="size-4" aria-hidden="true" />
        </template>
        {{ __("Back to Tickets") }}
      </Button>
    </TaskyState>
  </div>
</template>

<script setup lang="ts">
import TicketIcon from "@/components/icons/TicketIcon.vue";
import TaskyState from "@/components/TaskyState.vue";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import TicketActivityPanel from "@/components/ticket-agent/TicketActivityPanel.vue";
import TicketHeader from "@/components/ticket-agent/TicketHeader.vue";
import TicketSidebar from "@/components/ticket-agent/TicketSidebar.vue";
import SetContactPhoneModal from "@/components/ticket/SetContactPhoneModal.vue";
import { useActiveViewers } from "@/composables/realtime";
import {
  SlaTimeLeftSymbol,
  useSlaTimeLeft,
} from "@/composables/useSlaTimeLeft";
import {
  reloadTicket,
  revalidateTicket,
  useTicket,
} from "@/composables/useTicket";
import { ticketsToNavigate } from "@/composables/useTicketNavigation";
import { globalStore } from "@/stores/globalStore";
import { useTelephonyStore } from "@/stores/telephony";
import {
  ActivitiesSymbol,
  AssigneeSymbol,
  Customizations,
  CustomizationSymbol,
  RecentSimilarTicketsSymbol,
  Resource,
  TicketContactSymbol,
  TicketSymbol,
} from "@/types";
import {
  createResource,
  LoadingIndicator,
  toast,
  usePageMeta,
} from "frappe-ui";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  watch,
} from "vue";
import { useMediaQuery } from "@vueuse/core";
import { useRoute } from "vue-router";
import { showCommentBox, showEmailBox } from "./modalStates";

const telephonyStore = useTelephonyStore();

const { $socket } = globalStore();

const props = defineProps({
  ticketId: {
    type: String,
    required: true,
  },
});
const route = useRoute();
const showPhoneModal = ref(false);
const detailsOpen = ref(false);
// below lg the side panel is a sheet, opened from the header or by a field shortcut
const isSheet = useMediaQuery("(max-width: 1023.98px)");
provide("openTicketDetails", async () => {
  if (!isSheet.value || detailsOpen.value) return;
  detailsOpen.value = true;
  await nextTick();
});

const ticketComposable = computed(() => useTicket(props.ticketId));
const ticket = computed(() => ticketComposable.value.ticket);
const customizations: Resource<Customizations> = createResource({
  url: "helpdesk.helpdesk.doctype.hd_ticket.api.get_ticket_customizations",
  cache: ["HD Ticket", "customizations"],
  auto: true,
});

provide(TicketSymbol, ticket);
provide(
  SlaTimeLeftSymbol,
  useSlaTimeLeft(() => (ticket.value.doc ? [ticket.value.doc] : []))
);

provide(
  AssigneeSymbol,
  computed(() => ticketComposable.value.assignees)
);
provide(
  TicketContactSymbol,
  computed(() => ticketComposable.value.contact)
);
provide(
  CustomizationSymbol,
  computed(() => customizations)
);
provide(
  RecentSimilarTicketsSymbol,
  computed(() => ticketComposable.value.recentSimilarTickets)
);
provide(
  ActivitiesSymbol,
  computed(() => ticketComposable.value.activities)
);
provide("makeCall", () => {
  if (
    !ticketComposable.value.contact.data?.mobile_no &&
    !ticketComposable.value.contact.data?.phone
  ) {
    showPhoneModal.value = true;
    return;
  }
  telephonyStore.makeCall({
    number:
      ticketComposable.value.contact.data?.phone ||
      ticketComposable.value.contact.data?.mobile_no,
    doctype: "HD Ticket",
    docname: props.ticketId,
  });
});
provide("refreshTicket", () => reloadTicket(props.ticketId));
provide("onCallEnded", () => reloadTicket(props.ticketId));

const viewerComposable = computed(() => useActiveViewers(ticket.value.name));
const viewers = computed(
  () => viewerComposable.value.currentViewers[props.ticketId] || []
);
const { startViewing, stopViewing } = viewerComposable.value;

// handling for faster navigation between tickets
watch(
  () => route.params.ticketId,
  (newTicketId, oldTicketId) => {
    if (newTicketId === oldTicketId) return;

    if (oldTicketId) stopViewing(oldTicketId as string);
    startViewing(newTicketId as string);

    // Switching to an already-visited ticket: show its cached conversation and
    // refresh it in the background in case it changed while we were elsewhere.
    if (oldTicketId) revalidateTicket(newTicketId as string);
  },
  { immediate: true }
);

type TicketUpdateData = {
  ticket_id: string;
  user: string;
  field: string;
  value: string;
};

onMounted(() => {
  // Revisiting a ticket: show the cached conversation immediately and refresh it
  // in place, since a reply may have arrived while the socket listener was off.
  revalidateTicket(props.ticketId);

  ticketsToNavigate.update({
    params: {
      ticket: props.ticketId,
      current_view: route.query.view as string,
    },
  });
  ticketsToNavigate.reload();
  ticket.value.markSeen.reload();

  $socket.on("ticket_update", (data: TicketUpdateData) => {
    if (data.ticket_id === ticket.value?.name) {
      // Notify the user about the update
      toast.info(`User ${data.user} updated ${data.field} to ${data.value}`);
    }
  });

  $socket.on("helpdesk:ticket-comment", (data: { ticket_id: string }) => {
    if (data.ticket_id == props.ticketId) {
      ticketComposable.value.activities.reload();
    }
  });

  $socket.on("helpdesk:ticket-update", (data: { ticket_id: string }) => {
    if (data.ticket_id == props.ticketId) {
      reloadTicket(props.ticketId);
    }
  });
});

onBeforeUnmount(() => {
  stopViewing(props.ticketId);
  showEmailBox.value = false;
  showCommentBox.value = false;

  $socket.off("ticket_update");
  $socket.off("helpdesk:ticket-comment");
  $socket.off("helpdesk:ticket-update");
});
usePageMeta(() => {
  if (!ticket.value?.doc?.name) {
    return { title: props.ticketId };
  }

  return {
    title: props.ticketId + " - " + (ticket.value?.doc?.subject ?? ""),
  };
});
</script>
