<template>
  <div class="flex flex-col">
    <LayoutHeader v-if="ticket.doc?.name">
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" />
      </template>
      <template #right-header>
        <div class="absolute right-0 pr-2">
          <Dropdown :options="dropdownOptions">
            <template #default="{ open }">
              <Button :label="ticket.doc.status">
                <template #prefix>
                  <component
                    :is="statusLook.icon"
                    class="size-4"
                    :class="INK[statusLook.tone]"
                    aria-hidden="true"
                  />
                </template>
                <template #suffix>
                  <FeatherIcon
                    :name="open ? 'chevron-up' : 'chevron-down'"
                    class="h-4"
                  />
                </template>
              </Button>
            </template>
          </Dropdown>
        </div>
      </template>
    </LayoutHeader>
    <header
      class="flex h-12 items-center justify-between py-[7px] px-3 border-b"
      v-if="ticket.doc?.name"
    >
      <!-- left side -->
      <div class="flex items-center gap-2 max-w-[50%]">
        <AssignTo :hide-label="true" />
      </div>
      <!-- right side -->
      <div class="flex items-center gap-2">
        <CustomActions
          v-if="mobileCustomActions.length"
          :actions="mobileCustomActions"
        />
      </div>
    </header>
    <!-- the subject in full and the same line as on desktop (Phase 15) -->
    <div
      v-if="ticket.doc?.name"
      class="border-b border-outline-gray-1 px-4 py-3"
    >
      <h1
        class="text-lg font-semibold leading-6 text-ink-gray-9 [overflow-wrap:anywhere]"
      >
        {{ ticket.doc.subject }}
      </h1>
      <p
        class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm text-ink-gray-6"
      >
        <span class="text-ink-gray-8">{{
          ticket.doc.contact || ticket.doc.raised_by
        }}</span>
        <span v-if="ticket.doc.customer">{{ ticket.doc.customer }}</span>
        <TaskyBadge v-if="priority" v-bind="priority" />
        <TaskyBadge v-if="due" :tone="due.tone" :icon="due.icon">
          {{ due.label }}
          <span class="sr-only">, {{ due.hint }}</span>
        </TaskyBadge>
      </p>
    </div>
    <div v-if="ticket.doc?.name" class="flex flex-1 overflow-x-hidden">
      <div class="flex flex-1 flex-col overflow-x-hidden">
        <div class="flex-1 flex flex-col">
          <Tabs
            :modelValue="tabIndex"
            :tabs="tabs"
            @update:modelValue="changeTabTo"
            class="[&_[role='tab']]:px-0 [&_[role='tablist']]:px-5 [&_[role='tablist']]:gap-7.5"
          >
            <template #tab-panel="{ tab }">
              <!-- the same side panel as on desktop, as tabs -->
              <TicketDetailsTab v-if="tab.name === 'details'" />
              <div
                v-else-if="tab.name === 'chat'"
                class="flex h-[calc(100dvh-15rem)] flex-col"
              >
                <CopilotThread
                  :ticket="String(ticket.doc.name)"
                  :request="ticketRequest(ticket.doc)"
                  wide
                />
              </div>

              <!-- the conversation with the customer, or everything that happened -->
              <TicketAgentActivities
                v-else
                ref="ticketAgentActivitiesRef"
                :activities="
                  tab.name === 'customer'
                    ? filterConversation('all')
                    : filterActivities('activity')
                "
                :title="tab.label"
                :ticket-status="ticket.doc?.status"
                :compact="tab.name === 'activity'"
                @open="changeTabTo(1)"
                @update="() => reloadTicket(props.ticketId)"
                @email:reply="
                  (e) => {
                    communicationAreaRef.replyToEmail(e);
                  }
                "
              />
            </template>
          </Tabs>
          <!-- the chat has its own box; replies and comments belong to the other tabs -->
          <CommunicationArea
            v-show="tabs[tabIndex]?.name !== 'chat'"
            class="sticky bottom-0 z-50 bg-surface-base"
            ref="communicationAreaRef"
            v-model="ticket.doc"
            :ticketId="ticket.doc?.name"
            :to-emails="[ticket.doc.raised_by]"
            :cc-emails="[]"
            :bcc-emails="[]"
            :key="ticket.doc?.name"
            @update="
              () => {
                reloadTicket(props.ticketId);
                tabIndex !== 0 &&
                  ticketAgentActivitiesRef?.scrollToLatestActivity();
              }
            "
          />
        </div>
      </div>
    </div>

    <Dialog v-model:open="showSubjectDialog">
      <template #title>
        <h3>{{ __("Rename") }}</h3>
      </template>
      <template #default>
        <FormControl
          v-model="subjectInput"
          :type="'text'"
          size="sm"
          variant="subtle"
          :disabled="false"
          :label="__('New Subject')"
        />
      </template>
      <template #actions>
        <Button
          variant="solid"
          :disabled="!subjectInput"
          :loading="ticket.setValue.loading"
          @click="
            () => {
              ticket.setValue.submit({ subject: subjectInput });
              showSubjectDialog = false;
            }
          "
        >
          {{ __("Confirm") }}
        </Button>
        <Button class="ml-2" @click="showSubjectDialog = false">
          {{ __("Close") }}
        </Button>
      </template>
    </Dialog>
    <SetContactPhoneModal
      v-model="showPhoneModal"
      :name="contact.data?.name"
      @onUpdate="() => reloadTicket(props.ticketId)"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Breadcrumbs,
  call,
  createResource,
  Dialog,
  Dropdown,
  FormControl,
  Tabs,
  toast,
} from "frappe-ui";
import {
  computed,
  ComputedRef,
  h,
  onMounted,
  onUnmounted,
  PropType,
  provide,
  ref,
  watchEffect,
} from "vue";

import { CommunicationArea, LayoutHeader } from "@/components";
import {
  ActivityIcon,
  CommentIcon,
  DetailsIcon,
  EmailIcon,
  PhoneIcon,
} from "@/components/icons";
import { TicketAgentActivities } from "@/components/ticket";

import CustomActions from "@/components/CustomActions.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { INK } from "@/components/tone";
import {
  dueBadge,
  priorityBadge,
  statusBadge,
} from "@/pages/ticket/ticketMeta";
import AssignTo from "@/components/ticket-agent/AssignTo.vue";
import CopilotThread from "@/components/ticket-agent/CopilotThread.vue";
import { ticketRequest } from "@/components/ticket-agent/ticketRequest";
import TicketDetailsTab from "@/components/ticket-agent/TicketDetailsTab.vue";
import CopilotIcon from "~icons/lucide/bot";
import SetContactPhoneModal from "@/components/ticket/SetContactPhoneModal.vue";
import { setupCustomizations } from "@/composables/formCustomisation";
import { useScreenSize } from "@/composables/screen";
import { useActiveTabManager } from "@/composables/useActiveTabManager";
import {
  SlaTimeLeftSymbol,
  useSlaTimeLeft,
} from "@/composables/useSlaTimeLeft";
import {
  reloadTicket,
  revalidateTicket,
  useTicket,
} from "@/composables/useTicket";
import { useTicketActivities } from "@/composables/useTicketActivities";
import { globalStore } from "@/stores/globalStore";
import { useTelephonyStore } from "@/stores/telephony";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import {
  ActivitiesSymbol,
  AssigneeSymbol,
  Customizations,
  CustomizationSymbol,
  RecentSimilarTicketsSymbol,
  Resource,
  TabObject,
  TicketContactSymbol,
  TicketSymbol,
} from "@/types";
import { HDTicketStatus } from "@/types/doctypes";
import { storeToRefs } from "pinia";
import { useRouter } from "vue-router";

const telephonyStore = useTelephonyStore();
const { isCallingEnabled } = storeToRefs(telephonyStore);

const ticketStatusStore = useTicketStatusStore();
const router = useRouter();
const { $dialog } = globalStore();

const ticketAgentActivitiesRef = ref<InstanceType<
  typeof TicketAgentActivities
> | null>(null);
const communicationAreaRef = ref<InstanceType<typeof CommunicationArea> | null>(
  null
);

const subjectInput = ref(null);
const showPhoneModal = ref(false);
const customActions = ref([]);

type ticketId = string | number;

const props = defineProps({
  ticketId: {
    type: [String, Number] as PropType<ticketId>,
    required: true,
  },
});

const ticketComposable = computed(() => useTicket(props.ticketId));
const ticket = computed(() => ticketComposable.value.ticket);
const contact = computed(() => ticketComposable.value.contact);
const activities = computed(() => ticketComposable.value.activities);

const customizations: Resource<Customizations> = createResource({
  url: "helpdesk.helpdesk.doctype.hd_ticket.api.get_ticket_customizations",
  cache: ["HD Ticket", "customizations"],
  auto: true,
});

function updateField(name: string, value: string) {
  ticket.value.setValue.submit({ [name]: value });
}

const customizationCtx = computed(() => ({
  doc: ticket.value?.doc,
  call,
  router,
  toast,
  $dialog,
  updateField,
  createToast: toast.create,
}));

watchEffect(async () => {
  if (customizations.data) {
    await setupCustomizations(customizations.data, customizationCtx.value);
    customActions.value = [...(customizations.data?._customActions || [])];
  }
});

// On mobile, collapse all custom actions into a single three-dot group
const mobileCustomActions = computed(() => {
  if (!customActions.value.length) return [];

  const items: { label: string; onClick: () => void }[] = [];

  for (const action of customActions.value) {
    if (action.group) {
      // Grouped action (with or without buttonLabel) — flatten its items
      for (const item of action.items || []) {
        items.push({ label: item.label, onClick: item.onClick });
      }
    } else {
      // Normal standalone button
      items.push({ label: action.label, onClick: action.onClick });
    }
  }

  if (!items.length) return [];

  return [{ group: "Actions", hideLabel: true, items }];
});

provide(TicketSymbol, ticket);
const slaClock = useSlaTimeLeft(() =>
  ticket.value.doc ? [ticket.value.doc] : []
);
provide(SlaTimeLeftSymbol, slaClock);

// the line under the subject, as on desktop (Phase 15)
const priority = computed(() => priorityBadge(ticket.value.doc?.priority));
const due = computed(() => {
  const doc = ticket.value.doc;
  if (!doc) return null;
  return dueBadge(
    doc,
    doc.status_category === "Paused",
    (clock) => slaClock.workingLeft(doc.name, clock),
    slaClock.now.value
  );
});
const statusLook = computed(() =>
  statusBadge(
    ticket.value.doc?.status ?? "",
    ticketStatusStore.getStatus(ticket.value.doc?.status)?.category ??
      ticket.value.doc?.status_category
  )
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
provide("communicationArea", communicationAreaRef);
provide("makeCall", () => {
  if (!contact.value.data?.mobile_no && !contact.value.data?.phone) {
    showPhoneModal.value = true;
    return;
  }
  telephonyStore.makeCall({
    number: contact.value.data?.phone || contact.value.data?.mobile_no,
    doctype: "HD Ticket",
    docname: props.ticketId,
  });
});
provide("ticketId", props.ticketId);
provide("refreshTicket", () => reloadTicket(props.ticketId));
provide("onCallEnded", () => reloadTicket(props.ticketId));

const { isMobileView } = useScreenSize();

const showSubjectDialog = ref(false);

const breadcrumbs = computed(() => {
  let items = [{ label: __("Tickets"), route: { name: "TicketsAgent" } }];
  // the number here; the subject has its own line below, in full
  items.push({
    label: `#${ticket.value.doc?.name ?? ""}`,
    route: { name: "TicketAgent" },
  });
  return items;
});

const dropdownOptions = computed(() =>
  ticketStatusStore.statuses.data?.map((o: HDTicketStatus) => ({
    label: o.label_agent,
    value: o.label_agent,
    onClick: () => ticket.value.setValue.submit({ status: o.label_agent }),
    icon: () => {
      const look = statusBadge(o.label_agent, o.category);
      return h(look.icon, {
        class: ["size-4", INK[look.tone]],
        "aria-hidden": "true",
      });
    },
  }))
);

const tabs: ComputedRef<TabObject[]> = computed(() => {
  const _tabs = [
    // the ticket opens on its chat (Phase 12), then the customer, everything, its details
    {
      name: "chat",
      label: __("Chat"),
      icon: CopilotIcon,
      condition: () => isMobileView.value,
    },
    {
      name: "customer",
      label: __("Customer"),
      icon: EmailIcon,
    },
    {
      name: "activity",
      label: __("Activity"),
      icon: ActivityIcon,
    },
    {
      name: "details",
      label: __("Details"),
      icon: DetailsIcon,
      condition: () => isMobileView.value,
    },
  ];
  return _tabs;
});

const { tabIndex, changeTabTo } = useActiveTabManager(tabs);

const { filterActivities, filterConversation } = useTicketActivities(
  activities,
  computed(() => ticket.value?.doc)
);

onMounted(() => {
  document.title = props.ticketId;
  // Revisiting a ticket: show the cached conversation immediately and refresh it
  // in place (mobile has no live socket refresh to keep the cache current).
  revalidateTicket(props.ticketId);
});

onUnmounted(() => {
  document.title = "TBO Support";
});
</script>
<style scoped>
:deep(.breadcrumb-item span),
:deep(a span) {
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  white-space: normal !important;
}
</style>
