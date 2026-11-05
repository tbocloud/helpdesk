<template>
  <div v-if="ticket.doc?.name" class="flex min-h-0 min-w-0 flex-1 flex-col">
    <TicketHeader
      :viewers="viewers"
      :details-open="isSheet ? detailsOpen : !detailsHidden"
      @toggle-details="toggleDetails"
    />
    <!-- a phone's header is one line: the subject, who it is from and who has it come here -->
    <div
      v-if="isMobileView"
      class="shrink-0 border-b border-outline-gray-1 px-4 py-2.5"
    >
      <h1
        class="line-clamp-2 text-base font-semibold leading-6 text-ink-gray-9 [overflow-wrap:anywhere]"
      >
        {{ ticket.doc.subject }}
      </h1>
      <div class="mt-1 flex items-center gap-2 text-sm text-ink-gray-6">
        <span class="min-w-0 truncate">
          <span class="text-ink-gray-8">{{
            ticket.doc.contact || ticket.doc.raised_by
          }}</span>
          <template v-if="ticket.doc.customer">
            · {{ ticket.doc.customer }}</template
          >
        </span>
        <TaskyBadge v-if="priority" v-bind="priority" />
        <AssignTo hide-label quiet class="ms-auto max-w-[45%]" />
      </div>
    </div>
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <!-- the ticket as one conversation (Phase 16): where it stands, the thread, one box to
           write in; keyed so each ticket starts with its own state -->
      <div
        :key="String(ticket.doc.name)"
        class="flex min-w-0 flex-1 flex-col overflow-hidden"
      >
        <TicketStanding />
        <TicketConversation
          @reply="(target) => composerRef?.replyToEmail(target)"
        />
        <TicketComposer
          ref="composerRef"
          @sent="ticketComposable.activities.reload()"
        />
      </div>

      <!-- Details: inline with a resizer when there is room, a sheet otherwise -->
      <TicketSidebar
        v-model:open="detailsOpen"
        :sheet="isSheet"
        :hidden="!isSheet && detailsHidden"
      />
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
import TicketComposer from "@/components/ticket-inbox/TicketComposer.vue";
import TicketConversation from "@/components/ticket-inbox/TicketConversation.vue";
import TicketStanding from "@/components/ticket-inbox/TicketStanding.vue";
import { refreshInbox } from "@/components/ticket-inbox/inbox";
import TicketHeader from "@/components/ticket-agent/TicketHeader.vue";
import AssignTo from "@/components/ticket-agent/AssignTo.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { useScreenSize } from "@/composables/screen";
import { priorityBadge } from "@/pages/ticket/ticketMeta";
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
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  watch,
  type Ref,
} from "vue";
import { useMediaQuery, useStorage } from "@vueuse/core";
import { useRoute } from "vue-router";
import { composerMode, showCommentBox, showEmailBox } from "./modalStates";

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
const composerRef = ref<InstanceType<typeof TicketComposer> | null>(null);
const { isMobileView } = useScreenSize();
// the side panel is a sheet below lg, or below 1440 px when the inbox list sits beside the ticket
const listBeside = inject<Ref<boolean>>("inboxListShown", ref(false));
const narrow = useMediaQuery("(max-width: 1023.98px)");
const crowded = useMediaQuery("(max-width: 1439.98px)");
const isSheet = computed(
  () => narrow.value || (listBeside.value && crowded.value)
);
// from lg the panel sits beside the conversation; it can be hidden (Phase 15), per browser
const detailsHidden = useStorage("helpdesk-ticket-details-hidden", false);
function toggleDetails() {
  if (isSheet.value) detailsOpen.value = !detailsOpen.value;
  else detailsHidden.value = !detailsHidden.value;
}
provide("openTicketDetails", async () => {
  if (!isSheet.value || detailsOpen.value) return;
  detailsOpen.value = true;
  await nextTick();
});

const ticketComposable = computed(() => useTicket(props.ticketId));
const ticket = computed(() => ticketComposable.value.ticket);
const priority = computed(() => priorityBadge(ticket.value.doc?.priority));
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
    // every ticket opens with the reply box ready and nothing half-open from the last one
    composerMode.value = "reply";
    showEmailBox.value = false;
    showCommentBox.value = false;

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
// a change on the open ticket (a reply, the status, the assignee) shows in the inbox's row
watch(
  () => ticket.value?.doc?.modified,
  (now, before) => before && now !== before && refreshInbox()
);

usePageMeta(() => {
  if (!ticket.value?.doc?.name) {
    return { title: props.ticketId };
  }

  return {
    title: props.ticketId + " - " + (ticket.value?.doc?.subject ?? ""),
  };
});
</script>
