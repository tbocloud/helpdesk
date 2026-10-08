<template>
  <div v-if="ticket.data" class="flex flex-col">
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" class="-ml-0.5" />
      </template>
      <template #right-header>
        <CustomActions
          v-if="ticket.data._customActions"
          :actions="ticket.data._customActions"
        />
        <!-- secondary: replying is the page's main action -->
        <Button
          v-if="!isClosed"
          :label="__('Close ticket')"
          @click="handleClose()"
        >
          <template #prefix>
            <LucideCheck class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>
    <div class="flex h-full w-full overflow-hidden">
      <section class="flex min-w-0 flex-1 flex-col">
        <div
          v-if="outsideHourSettings.data?.show && !isDismissed"
          class="px-4 pt-4 md:px-10"
        >
          <Alert
            :title="outsideHourSettings.data?.msg"
            theme="yellow"
            class="text-p-sm [&_.size-4]:relative [&>.size-4]:top-[3.5px] [&_button>:first-child]:top-[2.25px] border border-outline-amber-2"
            @dismiss="dismissBanner"
          >
          </Alert>
        </div>
        <!-- a customization estimate waiting for the customer's answer -->
        <EstimateApprovalBanner
          :ticket-id="String(ticketId)"
          @decided="ticket.reload()"
        />
        <!-- Mobile: Conversation / Details tabs -->
        <Tabs
          v-if="isMobileView"
          v-model="activeTab"
          :tabs="tabs"
          class="min-h-0 flex-1 [&_[role='tablist']]:px-4"
        >
          <template #tab-panel="{ tab }">
            <TicketCustomerSidebar v-if="tab.name === 'details'" inline />
            <div v-else class="h-full overflow-y-auto">
              <TicketCustomerSummary :is-closed="isClosed" @reply="openReply" />
              <TicketConversation :show-header="false" />
            </div>
          </template>
        </Tabs>

        <!-- Desktop: summary and conversation scroll together -->
        <div v-else class="min-h-0 flex-1 overflow-y-auto">
          <TicketCustomerSummary :is-closed="isClosed" @reply="openReply" />
          <TicketConversation />
        </div>

        <div
          v-if="!isMobileView || activeTab === 0"
          class="w-full border-t border-outline-gray-2 px-4 py-3 md:px-10"
          @keydown.ctrl.enter.capture.stop="sendEmail"
          @keydown.meta.enter.capture.stop="sendEmail"
        >
          <TicketTextEditor
            v-if="!isClosed"
            ref="editor"
            v-model:attachments="attachments"
            v-model:content="editorContent"
            v-model:expand="isExpanded"
            :placeholder="__('Write a reply')"
            autofocus
            @clear="() => (isExpanded = false)"
            :uploadFunction="
              (file: any) => uploadFunction(file, 'HD Ticket', props.ticketId)
            "
          >
            <template #bottom-right>
              <Button
                :label="__('Send reply')"
                variant="solid"
                :disabled="$refs.editor?.editor?.isEmpty || send.loading"
                :loading="send.loading"
                @click="sendEmail"
              />
            </template>
          </TicketTextEditor>
          <p v-else class="text-p-sm text-ink-gray-6">
            {{ __("This ticket is closed, so it can't take new replies.") }}
            <RouterLink
              :to="{ name: 'TicketNew' }"
              class="rounded font-medium text-ink-gray-8 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              {{ __("Raise a new ticket") }}
            </RouterLink>
          </p>
        </div>
      </section>
      <TicketCustomerSidebar v-if="!isMobileView" />
    </div>
    <TicketFeedback v-model:open="showFeedbackDialog" />
  </div>
  <!-- first load: the layout is known, so a skeleton instead of a spinner -->
  <div
    v-else-if="ticket.loading"
    class="flex flex-col gap-4 px-4 pt-16 md:px-10"
    aria-busy="true"
    :aria-label="__('Loading ticket')"
  >
    <div class="h-6 w-2/3 animate-pulse rounded bg-surface-gray-2" />
    <div class="h-4 w-1/3 animate-pulse rounded bg-surface-gray-2" />
    <div class="h-20 w-full animate-pulse rounded-lg bg-surface-gray-2" />
    <div class="h-32 w-full animate-pulse rounded-lg bg-surface-gray-2" />
  </div>
</template>

<script setup lang="ts">
import { LayoutHeader } from "@/components";
import TicketCustomerSidebar from "@/components/ticket/TicketCustomerSidebar.vue";
import { setupCustomizations } from "@/composables/formCustomisation";
import { useActiveViewers } from "@/composables/realtime";
import { useScreenSize } from "@/composables/screen";
import { useConfigStore } from "@/stores/config";
import { globalStore } from "@/stores/globalStore";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import {
  errorText,
  isContentEmpty,
  isCustomerPortal,
  uploadFunction,
} from "@/utils";
import { ActivityIcon, DetailsIcon } from "@/components/icons";
import {
  Alert,
  Breadcrumbs,
  Button,
  call,
  createResource,
  Tabs,
  toast,
} from "frappe-ui";
import { __ } from "@/translation";
import {
  computed,
  defineAsyncComponent,
  onMounted,
  onUnmounted,
  provide,
  ref,
} from "vue";
import { useRouter } from "vue-router";
import { ITicket } from "./symbols";
import EstimateApprovalBanner from "./EstimateApprovalBanner.vue";
import TicketConversation from "./TicketConversation.vue";
import TicketCustomerSummary from "./TicketCustomerSummary.vue";
import TicketFeedback from "./TicketFeedback.vue";
const TicketTextEditor = defineAsyncComponent(
  () => import("./TicketTextEditor.vue")
);

interface P {
  ticketId: string;
}
const router = useRouter();
const props = defineProps<P>();

const { getStatus } = useTicketStatusStore();

const ticket = createResource({
  url: "helpdesk.helpdesk.doctype.hd_ticket.api.get_one",
  cache: ["Ticket", props.ticketId],
  params: {
    name: props.ticketId,
    is_customer_portal: isCustomerPortal.value,
  },
  auto: true,
  onSuccess: (data) => {
    data.status = getStatus(data.status)?.label_customer;
    setupCustomizations(ticket, {
      doc: data,
      call,
      router,
      toast,
      $dialog,
      updateField,
      createToast: toast.create,
    });
  },
  onError: () => {
    toast.error(__("Ticket not found."));
    router.replace("/my-tickets");
  },
});

provide(ITicket, ticket);
const editor = ref(null);
const editorContent = ref("");
const attachments = ref([]);
const showFeedbackDialog = ref(false);
const isExpanded = ref(false);

const { isMobileView } = useScreenSize();
const { $dialog, $socket } = globalStore();
const isDismissed = ref(false);

const activeTab = ref(0);
const tabs = computed(() => [
  { name: "activity", label: __("Conversation"), icon: ActivityIcon },
  { name: "details", label: __("Details"), icon: DetailsIcon },
]);

function getTodayKey() {
  return new Date().toISOString().split("T")[0];
}

function dismissBanner() {
  try {
    const todayKey = getTodayKey();
    localStorage.setItem(`dismissBanner_${props.ticketId}_${todayKey}`, "true");
    isDismissed.value = true;
  } catch (error) {
    console.error("Error saving banner dismissal:", error);
  }
}

onMounted(() => {
  try {
    const todayKey = getTodayKey();
    const dismissed = localStorage.getItem(
      `dismissBanner_${props.ticketId}_${todayKey}`
    );
    isDismissed.value = dismissed === "true";
    cleanupOldBannerDismissals();
  } catch (error) {
    console.error("Error reading banner dismissal:", error);
  }
});

// Clean up old banner dismissal localStorage keys
const cleanupOldBannerDismissals = () => {
  const CLEANUP_KEY = "lastBannerCleanup";
  const ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000;

  try {
    const lastCleanup = localStorage.getItem(CLEANUP_KEY);
    const now = Date.now();

    if (lastCleanup && now - parseInt(lastCleanup) < ONE_WEEK_MS) {
      return;
    }

    // Find and remove all dismissBanner keys
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith("dismissBanner_")) {
        keysToRemove.push(key);
      }
    }

    // Remove the keys
    keysToRemove.forEach((key) => localStorage.removeItem(key));

    // Update last cleanup timestamp
    localStorage.setItem(CLEANUP_KEY, now.toString());
  } catch (error) {
    console.error("Error cleaning up banner dismissals:", error);
  }
};

const outsideHourSettings = createResource({
  url: "helpdesk.helpdesk.doctype.hd_ticket.api.show_outside_hours_banner",
  cache: ["OutsideHourBanner", props.ticketId],
  params: {
    ticket_name: props.ticketId,
  },
  auto: true,
});

const send = createResource({
  url: "run_doc_method",
  debounce: 300,
  makeParams: () => ({
    dt: "HD Ticket",
    dn: props.ticketId,
    method: "create_communication_via_contact",
    args: {
      message: editorContent.value,
      attachments: attachments.value,
    },
  }),
  onSuccess: () => {
    editor.value.editor.commands.clearContent(true);
    attachments.value = [];
    isExpanded.value = false;
    ticket.reload();
  },
  onError: (error) => {
    // the draft stays in the editor, so sending again is the way forward
    toast.error(
      errorText(error, __("Your reply wasn't sent. Please try again."))
    );
  },
});

function openReply() {
  if (isMobileView.value) activeTab.value = 0;
  isExpanded.value = true;
}

function updateField(name, value, callback = () => {}) {
  updateTicket(name, value);
  callback();
}

function sendEmail() {
  if (isContentEmpty(editorContent.value) || send.loading) {
    return;
  }
  send.submit();
}

function updateTicket(fieldname: string, value: string) {
  createResource({
    url: "frappe.client.set_value",
    params: {
      doctype: "HD Ticket",
      name: props.ticketId,
      fieldname,
      value,
    },
    auto: true,
    onSuccess: () => {
      ticket.reload();
      toast.success(__("Ticket updated succesfully."));
    },
  });
}

function handleClose() {
  if (showFeedback.value) {
    showFeedbackDialog.value = true;
  } else {
    showConfirmationDialog();
  }
}

function showConfirmationDialog() {
  $dialog({
    title: __("Close this ticket?"),
    message: __(
      "Close it when your question is answered. A closed ticket can't take new replies."
    ),
    actions: [
      {
        label: __("Close ticket"),
        variant: "solid",
        onClick(close: Function) {
          ticket.data.status = "Closed";
          setValue.submit(
            { fieldname: "status", value: "Closed" },
            {
              onSuccess: () => {
                toast.success(__("Ticket closed successfully."));
              },
            }
          );
          close();
        },
      },
    ],
  });
}

const setValue = createResource({
  url: "frappe.client.set_value",
  debounce: 300,
  makeParams: (params) => {
    return {
      doctype: "HD Ticket",
      name: props.ticketId,
      fieldname: params.fieldname,
      value: params.value,
    };
  },
  onSuccess: () => {
    showFeedbackDialog.value = false;
    ticket.reload();
  },
});

const breadcrumbs = computed(() => {
  let items = [{ label: __("Tickets"), route: { name: "TicketsCustomer" } }];
  items.push({
    label: ticket.data?.subject,
    route: { name: "TicketCustomer" },
  });
  return items;
});

const isClosed = computed(() => ticket.data.status === "Closed");

// this handles whether the ticket was raised and then was closed without any reply from the agent.
const { isFeedbackMandatory } = useConfigStore();
const showFeedback = computed(() => {
  const hasAgentCommunication = ticket.data?.communications?.some(
    (c) => c.sender !== ticket.data.raised_by
  );
  return hasAgentCommunication && isFeedbackMandatory;
});
const { startViewing, stopViewing } = useActiveViewers(props.ticketId);

onMounted(() => {
  startViewing(props.ticketId);
  document.title = props.ticketId;

  $socket.on("helpdesk:ticket-update", ({ ticket_id }) => {
    if (ticket_id == props.ticketId) {
      ticket.reload();
    }
  });
});

onUnmounted(() => {
  stopViewing(props.ticketId);
  document.title = "TBO Support";
  $socket.off("helpdesk:ticket-update");
});
</script>
