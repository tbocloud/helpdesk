<template>
  <div>
    <LayoutHeader>
      <template #left-header>
        <ViewBreadcrumbs
          :label="__('Tickets')"
          :route-name="isCustomerPortal ? 'TicketsCustomer' : 'TicketsAgent'"
          :options="dropdownOptions"
          :dropdown-actions="(view) => viewActions(view, viewDialogConfig)"
          :current-view="currentView"
        />
      </template>
      <template #right-header>
        <RouterLink
          class="inline-flex"
          :to="{ name: isCustomerPortal ? 'TicketNew' : 'TicketAgentNew' }"
        >
          <Button
            class="rtl:flex-row-reverse"
            :label="__('New ticket')"
            theme="gray"
            variant="solid"
          >
            <template #prefix>
              <LucidePlus class="h-4 w-4" />
            </template>
          </Button>
        </RouterLink>
      </template>
    </LayoutHeader>
    <TicketSummaryStrip v-if="!isCustomerPortal" ref="summaryRef" />
    <ListViewBuilder
      ref="listViewRef"
      :options="options"
      @row-click="
        (row) =>
          $router.push({
            name: isCustomerPortal ? 'TicketCustomer' : 'TicketAgent',
            params: { ticketId: row },
          })
      "
    >
      <template v-if="!isCustomerPortal" #mobile-row="{ row }">
        <RouterLink
          :to="{
            name: 'TicketAgent',
            params: { ticketId: row.name },
            query: { view: route.query.view },
          }"
          class="flex flex-col gap-1.5 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
        >
          <span class="flex items-start justify-between gap-3">
            <span
              class="min-w-0 flex-1 truncate text-base text-ink-gray-9"
              :class="isUnseen(row) ? 'font-semibold' : 'font-medium'"
            >
              {{ row.subject }}
            </span>
            <component
              :is="slaCell(row, 'resolution', row.resolution_by)"
              v-if="row.resolution_by"
            />
          </span>
          <span
            class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-6"
          >
            <EscalationBadge
              v-if="row.custom_escalation_level"
              :level="row.custom_escalation_level"
            />
            <span class="font-mono tabular-nums text-ink-gray-5">
              #{{ row.name }}
            </span>
            <span v-if="row.customer" class="min-w-0 truncate">
              {{ row.customer }}
            </span>
            <span class="flex items-center gap-1.5 text-ink-gray-7">
              <IndicatorIcon :class="getStatus(row.status)?.parsed_color" />
              {{ getStatus(row.status)?.label_agent ?? row.status }}
            </span>
            <component :is="priorityCell(row.priority)" />
            <MultipleAvatar
              v-if="row._assign"
              :avatars="row._assign"
              hide-name
              class="ml-auto"
            />
          </span>
        </RouterLink>
      </template>
      <template v-else #mobile-row="{ row }">
        <RouterLink
          :to="{ name: 'TicketCustomer', params: { ticketId: row.name } }"
          class="flex flex-col gap-1.5 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
        >
          <span
            class="min-w-0 truncate text-base text-ink-gray-9"
            :class="isUnseen(row) ? 'font-semibold' : 'font-medium'"
          >
            {{ row.subject }}
          </span>
          <span
            class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-6"
          >
            <TaskyBadge v-bind="customerStatus.badge(row.status)" />
            <span class="font-mono tabular-nums text-ink-gray-5">
              #{{ row.name }}
            </span>
            <span class="ml-auto shrink-0">
              {{ __("Updated {0}", [timeAgo(row.modified)]) }}
            </span>
          </span>
        </RouterLink>
      </template>
      <template v-if="hasActiveFilters" #empty-actions>
        <Button
          :label="__('Clear filters')"
          @click="listViewRef?.clearFilters()"
        >
          <template #prefix>
            <LucideX class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
      <template v-else-if="isCustomerPortal" #empty-actions>
        <RouterLink class="inline-flex" :to="{ name: 'TicketNew' }">
          <Button :label="__('New ticket')" variant="solid">
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </RouterLink>
      </template>
    </ListViewBuilder>
    <ExportModal
      v-model="showExportModal"
      :rowCount="$refs.listViewRef?.list?.data?.total_count ?? 0"
      @update="
        ({ export_type, export_all }) => exportRows(export_type, export_all)
      "
    />
    <ViewModal
      v-if="viewDialogConfig.show"
      v-model="viewDialogConfig"
      @update="onViewModalUpdate"
    />
    <BulkReplyModal
      v-model="showBulkReplyModal"
      :selections="listSelections"
      @success="listViewRef?.unselectAll()"
    />
  </div>
</template>

<script setup lang="ts">
import { LayoutHeader, ListViewBuilder, MultipleAvatar } from "@/components";
import { TicketIcon } from "@/components/icons";
import IndicatorIcon from "@/components/icons/IndicatorIcon.vue";
import BulkReplyModal from "@/components/ticket-agent/BulkReplyModal.vue";
import TicketSummaryStrip from "@/components/ticket-agent/TicketSummaryStrip.vue";
import ExportModal from "@/components/ticket/ExportModal.vue";
import ViewBreadcrumbs from "@/components/ViewBreadcrumbs.vue";
import { normalizeFilters } from "@/components/view-controls/filter";
import ViewModal from "@/components/ViewModal.vue";
import { currentView, useView } from "@/composables/useView";
import { useAuthStore } from "@/stores/auth";
import { globalStore } from "@/stores/globalStore";
import TaskyBadge from "@/components/TaskyBadge.vue";
import EscalationBadge from "@/components/EscalationBadge.vue";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { View } from "@/types";
import { useSlaTimeLeft } from "@/composables/useSlaTimeLeft";
import {
  dateFormat,
  dateTooltipFormat,
  isCustomerPortal,
  timeAgo,
} from "@/utils";
import { Badge, Button, Tooltip, usePageMeta } from "frappe-ui";
import { computed, h, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  firstReplyFact,
  resolutionFact,
  useCustomerStatus,
  type Fact,
} from "./customerStatus";
import LucideX from "~icons/lucide/x";
import {
  priorityBadge,
  resolutionSla,
  responseSla,
  slaBadge,
  slaHint,
} from "./ticketMeta";

const router = useRouter();
const route = useRoute();

const {
  getCurrentUserViews,
  publicViews,
  pinnedViews,
  findView,
  standardViews,
  viewActions,
  handleView,
  resetViewDialog,
} = useView("HD Ticket");

const activeView = computed(() => findView(route.query.view as string).value);
const hasActiveFilters = computed(
  () => Object.keys(listViewRef.value?.list?.params?.filters || {}).length > 0
);

const { $socket } = globalStore();
const { isManager, userId } = useAuthStore();

const listViewRef = ref(null);
const summaryRef = ref<InstanceType<typeof TicketSummaryStrip> | null>(null);
const showExportModal = ref(false);

const { getStatus } = useTicketStatusStore();
const customerStatus = useCustomerStatus();

const listSelections = ref(new Set());

const showBulkReplyModal = ref(false);

const selectBannerActions = [
  {
    label: __("Bulk Reply"),
    icon: "corner-up-left",
    onClick: (selections: Set<string>) => {
      listSelections.value = new Set(selections);
      showBulkReplyModal.value = true;
    },
  },
  {
    label: __("Export"),
    icon: "lucide-download",
    onClick: (selections: Set<string>) => {
      listSelections.value = new Set(selections);
      showExportModal.value = true;
    },
  },
];

const options = computed(() => ({
  doctype: "HD Ticket",
  columnConfig: {
    subject: {
      custom: ({ row, item }) =>
        h("span", { class: "flex min-w-0 flex-1 items-center gap-1.5" }, [
          h(
            "span",
            { class: ["truncate", isUnseen(row) && "font-semibold"] },
            item
          ),
          // how far up the follow-up ladder its SLA breach has gone (docs/follow-ups.md)
          !isCustomerPortal.value && row.custom_escalation_level
            ? h(EscalationBadge, { level: row.custom_escalation_level })
            : null,
        ]),
    },
    status: {
      custom: ({ item }) => {
        if (isCustomerPortal.value) {
          return h(TaskyBadge, customerStatus.badge(item));
        }
        const status = getStatus(item);
        const label = status?.["label_agent"];
        return h(
          "div",
          { class: "flex items-center gap-1.5 justify-start w-full" },
          [
            h(IndicatorIcon, { class: status?.["parsed_color"] }),
            h("span", { class: "truncate flex-1 text-base" }, label),
          ]
        );
      },
    },
    agreement_status: {
      custom: ({ item }) => {
        return h(Badge, {
          label: __(item),
          theme: slaStatusColorMap[item],
          variant: "subtle",
        });
      },
    },
    response_by: {
      custom: ({ row, item }) =>
        isCustomerPortal.value
          ? factCell(firstReplyFact(row))
          : slaCell(row, "response", item),
    },
    resolution_by: {
      custom: ({ row, item }) =>
        isCustomerPortal.value
          ? factCell(resolutionFact(row, customerStatus.stage(row.status)))
          : slaCell(row, "resolution", item),
    },
    ...(isCustomerPortal.value
      ? {}
      : { priority: { custom: ({ item }) => priorityCell(item) } }),
  },
  isCustomerPortal: isCustomerPortal.value,
  selectable: true,
  showSelectBanner: true,
  selectBannerActions,
  emptyState: {
    title: __("No tickets found"),
    icon: h(TicketIcon, {
      class: "h-10 w-10",
    }),
    description:
      activeView.value?.public || activeView.value?.pinned
        ? __(
            "No tickets found for this view. Try adjusting your filters or creating a new view."
          )
        : hasActiveFilters.value
        ? __(
            "No tickets found for the applied filters. Try adjusting or clearing your filters."
          )
        : isCustomerPortal.value
        ? __("Raise a ticket and follow every reply from our team here.")
        : __(
            "Tickets from email and the customer portal show up here as they arrive."
          ),
  },
  rowRoute: {
    name: isCustomerPortal.value ? "TicketCustomer" : "TicketAgent",
    prop: "ticketId",
  },
  hideColumnSetting: false,
}));

function isUnseen(row: any) {
  const seenBy: string[] = row._seen ? JSON.parse(row._seen) : [];
  return !seenBy.includes(userId || "");
}

// the visible rows' working time left, in one request per page and refreshed every minute
const slaClock = useSlaTimeLeft(() =>
  isCustomerPortal.value ? [] : listViewRef.value?.list?.data?.data ?? []
);

function slaCell(row: any, clock: "response" | "resolution", deadline: string) {
  const now = slaClock.now.value;
  const state =
    clock === "response"
      ? responseSla(row, deadline, now)
      : resolutionSla(
          row,
          deadline,
          getStatus(row.status)?.category === "Paused",
          now
        );
  const workingLeft = slaClock.workingLeft(row.name, clock);
  const badge = slaBadge(state, deadline, workingLeft, now);
  if (!badge) return h("span");
  if (state !== "due") return h(TaskyBadge, badge);
  // a running clock: the exact deadline and the working time left, on hover and for screen readers
  const hint = slaHint(deadline, workingLeft);
  return h(Tooltip, { text: hint }, () =>
    h(TaskyBadge, { tone: badge.tone, icon: badge.icon }, () => [
      badge.label,
      h("span", { class: "sr-only" }, `, ${hint}`),
    ])
  );
}

// the customer's view of the same deadlines: "Overdue", never "Failed"
function factCell(fact: Fact | null) {
  if (!fact) return h("span");
  const badge = h(TaskyBadge, fact);
  return fact.at
    ? h(Tooltip, { text: dateFormat(fact.at, dateTooltipFormat) }, () => badge)
    : badge;
}

function priorityCell(priority: string) {
  const badge = priorityBadge(priority);
  return badge ? h(TaskyBadge, badge) : h("span");
}

async function exportRows(
  export_type: "CSV" | "Excel" = "Excel",
  export_all: boolean = false
) {
  const list = listViewRef.value?.list;
  if (!list) return;

  const fields = JSON.stringify(list.data.columns.map((f) => f.key));
  const order_by = list.params.order_by;

  // Resolve `@me` filters to the current session user before export
  const resolveAtMe = (entry: any) => {
    if (Array.isArray(entry)) return entry.map(resolveAtMe);
    if (entry === "@me") return userId;
    if (entry === "%@me%") return `%${userId}%`;
    return entry;
  };
  const conditions = normalizeFilters(list.params.filters).map(
    ([field, operator, value]) => [field, operator, resolveAtMe(value)]
  );
  let pageLength: number;

  if (export_all) {
    pageLength = list.data.total_count;
  } else {
    pageLength = listSelections.value.size;
    conditions.push(["name", "in", Array.from(listSelections.value)]);
  }
  const filters = JSON.stringify(conditions);

  window.location.href = `/api/method/frappe.desk.reportview.export_query?file_format_type=${export_type}&title=HD Ticket&doctype=HD Ticket&fields=${fields}&filters=${encodeURIComponent(
    filters
  )}&order_by=${order_by}&page_length=${pageLength}&start=0&view=Report&with_comment_count=1`;
  reset();
  showExportModal.value = false;
}

function reset(reload = false) {
  listViewRef.value?.unselectAll();
  listSelections.value?.clear();
  if (reload) listViewRef.value.reload();
}

const slaStatusColorMap = {
  Fulfilled: "gray",
  Failed: "red",
  "Resolution Due": "orange",
  "First Response Due": "orange",
  Paused: "blue",
};

let viewDialogConfig = reactive({
  show: false,
  view: {
    label: "",
    icon: "",
    name: "",
  },
  mode: "create",
});

const dropdownOptions = computed(() => {
  const items = [
    {
      group: __("Default Views"),
      items: [
        {
          label: __("List View"),
          icon: "lucide-align-justify",
          onClick: () =>
            router.push({
              name: isCustomerPortal.value ? "TicketsCustomer" : "TicketsAgent",
            }),
        },
      ],
    },
  ];

  // Saved Views
  if (getCurrentUserViews.value?.length !== 0) {
    items.push({
      group: __("Saved Views"),
      items: parseViews(getCurrentUserViews.value),
    });
  }
  if (pinnedViews.value?.length !== 0) {
    items.push({
      group: __("Private Views"),
      items: parseViews(pinnedViews.value),
    });
  }

  const allPublicViews = [
    ...(standardViews.value || []),
    ...(publicViews.value || []),
  ];

  const uniquePublicViews = Array.from(
    new Map(allPublicViews.map((v) => [v.name, v])).values()
  );

  items.push({
    group: __("Public Views"),
    items: parseViews(uniquePublicViews),
  });

  items.push({
    group: __("Create View"),
    hideLabel: true,
    items: [
      {
        label: __("Create View"),
        icon: "lucide-plus",
        onClick: () => {
          resetViewDialog(viewDialogConfig);
          viewDialogConfig.show = true;
        },
      },
    ],
  });

  return items;
});

function parseViews(views: View[]) {
  return views?.map((view) => {
    return {
      ...view,
      onClick: () => {
        currentView.value = {
          label: view.label,
          icon: view.icon,
        };
        router.push({
          name: view.route_name,
          query: {
            view: view.name,
          },
        });
      },
    };
  });
}

function onViewModalUpdate(viewInfo: any, action: string) {
  handleView(viewInfo, action, viewDialogConfig, () => listViewRef.value?.list);
}

onMounted(() => {
  if (!route.query.view) {
    currentView.value = {
      label: __("List"),
      icon: LucideAlignJustify,
    };
  }
  if (!isCustomerPortal.value) {
    $socket.on("helpdesk:new-ticket", () => {
      listViewRef.value?.reload();
      summaryRef.value?.reload();
    });
  }
});

onUnmounted(() => {
  if (!isCustomerPortal.value) {
    $socket.off("helpdesk:new-ticket");
  }
});

usePageMeta(() => {
  return {
    title: __("Tickets"),
  };
});
</script>
