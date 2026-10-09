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
                  <IndicatorIcon
                    :class="
                      ticketStatusStore.getStatus(ticket.doc.status)
                        ?.parsed_color
                    "
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
              <!-- the same side panel as on desktop, as a tab -->
              <TicketDetailsTab v-if="tab.name === 'details'" />

              <!-- Rest Activities -->
              <TicketAgentActivities
                v-else
                ref="ticketAgentActivitiesRef"
                :activities="filterActivities(tab.name)"
                :title="tab.label"
                :ticket-status="ticket.doc?.status"
                @update="() => reloadTicket(props.ticketId)"
                @email:reply="
                  (e) => {
                    communicationAreaRef.replyToEmail(e);
                  }
                "
              />
            </template>
          </Tabs>
          <CommunicationArea
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
  IndicatorIcon,
  PhoneIcon,
} from "@/components/icons";
import { TicketAgentActivities } from "@/components/ticket";

import CustomActions from "@/components/CustomActions.vue";
import AssignTo from "@/components/ticket-agent/AssignTo.vue";
import TicketDetailsTab from "@/components/ticket-agent/TicketDetailsTab.vue";
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
  items.push({
    label: ticket.value.doc?.subject,
    route: { name: "TicketAgent" },
  });
  return items;
});

const dropdownOptions = computed(() =>
  ticketStatusStore.statuses.data?.map((o: HDTicketStatus) => ({
    label: o.label_agent,
    value: o.label_agent,
    onClick: () => ticket.value.setValue.submit({ status: o.label_agent }),
    icon: () =>
      h(IndicatorIcon, {
        class: o.parsed_color,
      }),
  }))
);

const tabs: ComputedRef<TabObject[]> = computed(() => {
  const _tabs = [
    {
      name: "details",
      label: __("Details"),
      icon: DetailsIcon,
      condition: () => isMobileView.value,
    },
    {
      name: "activity",
      label: __("Activity"),
      icon: ActivityIcon,
    },
    {
      name: "email",
      label: __("Emails"),
      icon: EmailIcon,
    },
    {
      name: "comment",
      label: __("Comments"),
      icon: CommentIcon,
    },
  ];

  if (isCallingEnabled.value) {
    _tabs.push({
      name: "call",
      label: __("Calls"),
      icon: PhoneIcon,
    });
  }
  return _tabs;
});

const { tabIndex, changeTabTo } = useActiveTabManager(tabs);

const { filterActivities } = useTicketActivities(
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
