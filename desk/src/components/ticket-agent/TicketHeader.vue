<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex flex-col truncate">
        <Breadcrumbs :items="breadcrumbs" class="breadcrumbs -ml-0.5">
          <template #prefix="{ item }">
            <Icon
              v-if="item.icon"
              :icon="item.icon"
              class="mr-1 h-4 flex items-center justify-center self-center"
            />
          </template>
        </Breadcrumbs>
        <!-- a phone's header is one line: the ticket page shows the title under it -->
        <TicketTitle
          v-if="!isMobileView"
          @edit-subject="showSubjectDialog = true"
        />
      </div>
    </template>
    <template #right-header>
      <div class="flex items-center gap-2">
        <MultipleAvatar
          v-if="!isMobileView"
          :avatars="JSON.stringify(viewers)"
          size="md"
          :hide-name="true"
        />
        <!-- Navigation -->
        <TicketNavigation v-if="!isMobileView" :key="ticket?.name" />
        <!-- Custom Actions (on a phone they are in ⋯) -->
        <div v-if="normalActions.length && !isMobileView" class="flex gap-2">
          <Button v-for="action in normalActions" v-bind="action">
            <template v-if="action.icon" #prefix>
              <FeatherIcon :name="action.icon" class="h-4 w-4" />
            </template>
          </Button>
        </div>
        <div v-if="groupedWithLabelActions.length && !isMobileView">
          <div v-for="g in groupedWithLabelActions" :key="g.label">
            <Dropdown v-slot="{ open }" :options="g.action">
              <Button :label="g.label">
                <template #suffix>
                  <FeatherIcon
                    :name="open ? 'chevron-up' : 'chevron-down'"
                    class="h-4"
                  />
                </template>
              </Button>
            </Dropdown>
          </div>
        </div>
        <!-- Status (S) -->
        <Dropdown :options="statusDropdown" placement="right">
          <template #default="{ open }">
            <Button
              ref="statusRef"
              :label="ticket.doc.status"
              :aria-label="__('Status: {0}. Change status', ticket.doc.status)"
              aria-keyshortcuts="s"
            >
              <template #prefix>
                <component
                  :is="statusLook.icon"
                  class="size-4"
                  :class="INK[statusLook.tone]"
                  aria-hidden="true"
                />
              </template>
              <template #suffix>
                <LucideChevronDown
                  class="size-4 transition-transform"
                  :class="open && 'rotate-180'"
                  aria-hidden="true"
                />
              </template>
            </Button>
          </template>
        </Dropdown>
        <!-- who has it (Phase 12): pick someone working today -->
        <!-- on a phone it sits under the title (TicketAgent), so its A shortcut is bound once -->
        <AssignTo v-if="!isMobileView" hide-label quiet class="w-48" />
        <!-- Details: beside the conversation from lg (shown or hidden), a sheet below -->
        <!-- on a phone the icon alone; its label is still read out -->
        <Button
          :label="__('Details')"
          :aria-expanded="detailsOpen"
          :title="__('Show or hide the details')"
          @click="emit('toggle-details')"
        >
          <template v-if="isMobileView" #icon>
            <LucidePanelRight class="size-4" aria-hidden="true" />
          </template>
          <template v-else #prefix>
            <LucidePanelRight class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <!-- no Reply here (Phase 16): the box to write in is always under the conversation (R) -->
        <!-- Secondary, core and custom actions -->
        <Dropdown :options="groupedActions" placement="right">
          <Button
            icon="lucide-more-horizontal"
            :aria-label="__('More actions')"
          />
        </Dropdown>
      </div>
    </template>
  </LayoutHeader>
  <TicketMergeModal
    :ticket="ticket.doc"
    v-if="showMergeModal"
    v-model="showMergeModal"
    @update="ticket.reload()"
  />
  <TicketSubjectModal v-model="showSubjectDialog" />
  <ScheduleMeetingDialog
    v-if="ticket.doc?.name && showScheduleMeeting"
    v-model:open="showScheduleMeeting"
    reference-doctype="HD Ticket"
    :reference-name="String(ticket.doc.name)"
    initial-mode="now"
    @scheduled="onMeetingScheduled"
  />
</template>

<script setup lang="ts">
import { MultipleAvatar } from "@/components";
import LayoutHeader from "@/components/LayoutHeader.vue";
import TicketMergeModal from "@/components/ticket/TicketMergeModal.vue";
import { setupCustomizations } from "@/composables/formCustomisation";
import { useNotifyTicketUpdate } from "@/composables/realtime";
import { useShortcut } from "@/composables/shortcuts";
import { useView } from "@/composables/useView";
import { useAuthStore } from "@/stores/auth";
import { globalStore } from "@/stores/globalStore";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import {
  ActivitiesSymbol,
  CustomizationSymbol,
  TicketSymbol,
  View,
} from "@/types";
import { HDTicketStatus } from "@/types/doctypes";
import { INK } from "@/components/tone";
import { statusBadge } from "@/pages/ticket/ticketMeta";
import { copyToClipboard, getIcon } from "@/utils";
import LucideCopy from "~icons/lucide/copy";
import {
  Breadcrumbs,
  Button,
  call,
  createResource,
  Dropdown,
  toast,
} from "frappe-ui";
import {
  computed,
  ComputedRef,
  h,
  inject,
  onMounted,
  PropType,
  ref,
  useTemplateRef,
  watchEffect,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideListPlus from "~icons/lucide/list-plus";
import LucideVideo from "~icons/lucide/video";
import {
  meetingsChanged,
  meetingsEnabled,
} from "@/components/meetings/meetingsBus";
import ScheduleMeetingDialog from "@/components/meetings/ScheduleMeetingDialog.vue";
import { useScreenSize } from "@/composables/screen";
import { showCreateTask } from "@/pages/ticket/modalStates";
import LucideMerge from "~icons/lucide/merge";
import LucidePanelRight from "~icons/lucide/panel-right";
import AssignTo from "./AssignTo.vue";
import TicketNavigation from "./TicketNavigation.vue";
import TicketSubjectModal from "./TicketSubjectModal.vue";
import TicketTitle from "./TicketTitle.vue";
const { isAdmin } = useAuthStore();
const { isMobileView } = useScreenSize();
const { $dialog } = globalStore();

defineProps({
  viewers: {
    type: Array as PropType<string[]>,
    required: true,
  },
  /** The side panel sheet is open (below lg, where it isn't inline). */
  detailsOpen: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{ "toggle-details": [] }>();

const route = useRoute();
const router = useRouter();
const { findView } = useView("HD Ticket");
const ticketStatusStore = useTicketStatusStore();

const ticket = inject(TicketSymbol)!;
const customizations = inject(CustomizationSymbol)!;
const activities = inject(ActivitiesSymbol)!;
const showSubjectDialog = ref(false);
const showScheduleMeeting = ref(false);

// the Meetings card lists it, and the internal note shows in the activity
function onMeetingScheduled() {
  meetingsChanged.value++;
  activities.value?.reload();
}

const { notifyTicketUpdate } = useNotifyTicketUpdate(ticket.value?.name);
const statusDropdown = computed(() => {
  const statuses =
    ticketStatusStore.statuses.data?.filter((s) => s.enabled) || [];
  return statuses.map((o: HDTicketStatus) => ({
    label: o.label_agent,
    value: o.label_agent,
    onClick: () => {
      notifyTicketUpdate("Status", o.label_agent);
      if (ticket.value.doc.status === o.label_agent) return;
      ticket.value.setValue.submit(
        { status: o.label_agent },
        {
          onSuccess() {
            activities.value.reload();
          },
        }
      );
    },
    icon: () => {
      const look = statusBadge(o.label_agent, o.category);
      return h(look.icon, {
        class: ["size-4", INK[look.tone]],
        "aria-hidden": "true",
      });
    },
  }));
});
const breadcrumbs = computed(() => {
  let items = [{ label: __("Tickets"), route: { name: "TicketsAgent" } }];
  if (route.query.view) {
    const currView: ComputedRef<View> = findView(route.query.view as string);
    if (currView) {
      items.push({
        label: currView.value?.label,
        icon: getIcon(currView.value?.icon),
        route: { name: "TicketsAgent", query: { view: currView.value?.name } },
      });
    }
  }
  items.push({
    label: `#${ticket.value.doc?.name}`,
    onClick: () => {
      showSubjectDialog.value = true;
    },
  });
  return items;
});

function updateField(fieldname: string, value: string, callback = () => {}) {
  const doc = ticket.value;
  doc.setValue.submit({
    [fieldname]: value,
  });
  callback();
}

function handleDeleteTicket() {
  $dialog({
    title: __(`Delete ticket #${ticket?.value?.name}`),
    message: __(
      "Are you sure you want to delete this ticket? This is an irreversible action and cannot be undone."
    ),
    actions: [
      {
        label: __("Delete"),
        theme: "red",
        iconLeft: "trash-2",
        variant: "solid",
        onClick({ close }) {
          call("helpdesk.api.ticket.delete_ticket", {
            name: ticket?.value?.doc.name,
          })
            .then(() => {
              toast.success(__("Ticket deleted successfully."));
              router.push({ name: "TicketsAgent" });
            })
            .catch((err: any) => {
              toast.error(err || __("Failed to delete ticket."));
            });
          close();
        },
      },
    ],
  });
}

const ticketCount = createResource({
  url: "frappe.client.get_count",
  makeParams: () => ({
    doctype: "HD Ticket",
    filters: {
      status_category: ["!=", "Resolved"],
      is_merged: 0,
    },
  }),
  auto: true,
});
const showMergeModal = ref(false);
const showMergeOption = computed(() => {
  return (
    !ticket?.value?.doc?.is_merged &&
    ["Open", "Paused"].includes(ticket?.value?.doc?.status_category) &&
    ticketCount.data > 1
  );
});
// the status as an icon and a word in its tone (Phase 15), as in the list
const statusLook = computed(() =>
  statusBadge(
    ticket.value.doc.status,
    ticketStatusStore.getStatus(ticket.value.doc.status)?.category ??
      ticket.value.doc.status_category
  )
);

const defaultActions = computed(() => {
  let items: any[] = [
    {
      // the number is in the breadcrumb; copying it lives here (and on ⌘ .)
      label: __("Copy ticket ID"),
      icon: LucideCopy,
      onClick: () =>
        copyToClipboard(
          ticket.value.doc.name,
          __("Ticket #{0} copied to clipboard", ticket.value.doc.name)
        ),
    },
    {
      label: __("Create task"),
      icon: LucideListPlus,
      onClick: () => (showCreateTask.value = true),
    },
  ];

  if (meetingsEnabled.data) {
    items.push({
      label: __("Schedule Teams meeting"),
      icon: LucideVideo,
      onClick: () => (showScheduleMeeting.value = true),
    });
  }

  if (showMergeOption.value) {
    items.push({
      label: __("Merge Ticket"),
      icon: LucideMerge,
      condition: () => !ticket.value.doc.is_merged,
      onClick: () => (showMergeModal.value = true),
    });
  }

  return items;
});

const deleteAction = computed(() => {
  if (!isAdmin) return [];
  return [
    {
      label: __("Delete"),
      component: h(Button, {
        label: __("Delete"),
        variant: "ghost",
        iconLeft: "trash-2",
        theme: "red",
        style: "width: 100%; justify-content: flex-start;",
        onClick: handleDeleteTicket,
      }),
    },
  ];
});

const actions = ref<any[]>([]);
const normalActions = computed(() => {
  return actions.value.filter((action) => !action.group);
});

const groupedWithLabelActions = computed(() => {
  let _actions = [];

  actions.value
    .filter((action) => action.buttonLabel && action.group)
    .forEach((action) => {
      let groupIndex = _actions.findIndex(
        (a) => a.label === action.buttonLabel
      );
      if (groupIndex > -1) {
        _actions[groupIndex].action.push(action);
      } else {
        _actions.push({
          label: action.buttonLabel,
          action: [action],
        });
      }
    });
  return _actions;
});

// the ⋯ menu (Phase 12): the form scripts' groups (Customer site, Copilot and AI) first,
// then the ticket's own actions
const groupedActions = computed(() => [
  // a phone has no room for the form scripts' own buttons: they come first here
  ...(isMobileView.value && actions.value.some((a) => !a.group || a.buttonLabel)
    ? [
        {
          group: __("Actions"),
          items: actions.value
            .filter((a) => !a.group || a.buttonLabel)
            .map((a) => ({ label: a.label, icon: a.icon, onClick: a.onClick })),
        },
      ]
    : []),
  ...actions.value.filter((action) => action.group && !action.buttonLabel),
  {
    group: __("Ticket"),
    items: [...defaultActions.value, ...deleteAction.value],
  },
]);

const customizationCtx = computed(() => ({
  doc: ticket?.value?.doc,
  call,
  router,
  toast,
  $dialog: globalStore().$dialog,
  updateField,
  createToast: toast.create,
}));

// to manage the correct  customization context for actions, happens because of navigation between tickets using buttons
watchEffect(async () => {
  if (customizations.value?.data) {
    await setupCustomizations(
      customizations.value.data,
      customizationCtx.value
    );

    actions.value = [...(customizations.value?.data?._customActions || [])];
  }
});

const statusRef = useTemplateRef("statusRef");

onMounted(() => {
  useShortcut("s", () => {
    statusRef.value?.$el?.click();
  });
});
</script>

<style>
.breadcrumbs button {
  background-color: inherit !important;
  &:hover,
  &:focus {
    background-color: inherit !important;
  }
}
</style>
