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
            :label="isCustomerPortal ? __('Create') : __('New ticket')"
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
              :is="
                slaCell(
                  resolutionSla(row, row.resolution_by),
                  row.resolution_by
                )
              "
              v-if="row.resolution_by || row.resolution_date"
            />
          </span>
          <span
            class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-6"
          >
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
import TaskyBadge from "@/pages/tasky/components/TaskyBadge.vue";
import { priorityIcon } from "@/pages/tasky/taskMeta";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import { View } from "@/types";
import { isCustomerPortal, shortDuration } from "@/utils";
import { Badge, Button, dayjs, Tooltip, usePageMeta } from "frappe-ui";
import {
  computed,
  h,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  type Component,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucidePause from "~icons/lucide/pause";
import LucideX from "~icons/lucide/x";

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
        h(
          "span",
          { class: ["truncate flex-1", isUnseen(row) && "font-semibold"] },
          item
        ),
    },
    status: {
      custom: ({ item }) => {
        const status = getStatus(item);
        const label = isCustomerPortal.value
          ? status?.["label_customer"]
          : status?.["label_agent"];
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
      custom: ({ row, item }) => slaCell(responseSla(row, item), item),
    },
    resolution_by: {
      custom: ({ row, item }) => slaCell(resolutionSla(row, item), item),
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
        ? undefined
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

type SlaState = "failed" | "fulfilled" | "paused" | "due" | "none";

function responseSla(row: any, deadline: string): SlaState {
  if (!deadline) return "none";
  if (!row.first_responded_on && dayjs(deadline).isBefore(new Date()))
    return "failed";
  if (
    row.first_responded_on &&
    dayjs(row.first_responded_on).isBefore(deadline)
  )
    return "fulfilled";
  if (dayjs(row.first_responded_on).isAfter(deadline)) return "failed";
  return "due";
}

function resolutionSla(row: any, deadline: string): SlaState {
  if (getStatus(row.status)?.category === "Paused") return "paused";
  if (row.resolution_date)
    return dayjs(row.resolution_date).isBefore(dayjs(row.resolution_by))
      ? "fulfilled"
      : "failed";
  if (!deadline) return "none";
  return dayjs(deadline).isBefore(dayjs()) ? "failed" : "due";
}

// same window as SLA_RISK_HOURS in helpdesk/api/work.py ("at risk" tickets)
const SLA_RISK_HOURS = 4;

const SLA_LABELS: Record<Exclude<SlaState, "due" | "none">, string> = {
  failed: __("Failed"),
  fulfilled: __("Fulfilled"),
  paused: __("Paused"),
};
// the customer portal keeps its frappe-ui badge colours
const PORTAL_THEMES = {
  failed: "red",
  fulfilled: "gray",
  paused: "blue",
  due: "orange",
};
const SLA_BADGES: Record<
  Exclude<SlaState, "due" | "none">,
  { tone: "danger" | "neutral"; icon: Component }
> = {
  failed: { tone: "danger", icon: LucideCircleAlert },
  fulfilled: { tone: "neutral", icon: LucideCheck },
  paused: { tone: "neutral", icon: LucidePause },
};

function slaCell(state: SlaState, deadline: string) {
  if (state === "none") return h("span");
  const label = state === "due" ? shortDuration(deadline) : SLA_LABELS[state];
  const badge = isCustomerPortal.value
    ? h(Badge, { label, theme: PORTAL_THEMES[state], variant: "subtle" })
    : h(
        TaskyBadge,
        state === "due"
          ? {
              label: __("in {0}", [label]),
              icon: LucideClock,
              tone:
                dayjs(deadline).diff(dayjs(), "hour", true) <= SLA_RISK_HOURS
                  ? "warning"
                  : "neutral",
            }
          : { label, ...SLA_BADGES[state] }
      );
  // a running clock shows the exact deadline on hover
  return state === "due"
    ? h(Tooltip, { text: dayjs(deadline).format("LLLL") }, () => badge)
    : badge;
}

const PRIORITY_TONES: Record<string, "danger" | "warning"> = {
  Urgent: "danger",
  High: "warning",
};

function priorityCell(priority: string) {
  if (!priority) return h("span");
  return h(TaskyBadge, {
    label: __(priority),
    icon: priorityIcon(priority),
    tone: PRIORITY_TONES[priority] ?? "neutral",
  });
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
