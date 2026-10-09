<template>
  <div
    class="mx-auto flex h-full w-full max-w-screen-xl flex-col overflow-y-hidden"
  >
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" class="-ml-[2px]" />
      </template>
    </LayoutHeader>

    <TaskyState
      v-if="customer.get.error && !customer.doc"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t open this customer')"
      :message="
        errorText(
          customer.get.error,
          __('It may have been deleted or renamed, or you may not have access.')
        )
      "
      error
    >
      <Button :label="__('Retry')" @click="customer.reload()" />
      <Button
        :label="__('All customers')"
        @click="router.push({ name: 'CustomerList' })"
      />
    </TaskyState>

    <div
      v-else-if="!customer.doc?.name"
      class="flex items-center gap-3 px-5 pt-5"
      :aria-label="__('Loading')"
    >
      <span class="size-[52px] animate-pulse rounded-lg bg-surface-gray-2" />
      <div class="flex flex-col gap-2">
        <span class="h-5 w-48 animate-pulse rounded bg-surface-gray-2" />
        <span class="h-3.5 w-64 animate-pulse rounded bg-surface-gray-2" />
      </div>
    </div>

    <div v-else class="flex min-h-0 flex-1 flex-col gap-4">
      <PageInfo
        :avatar="{
          label: customer.doc.customer_name ?? '',
          image: customer.doc.image,
          shape: 'square',
        }"
        :doc-info="customerInfo"
      >
        <template #actions>
          <template v-if="hasPermission()">
            <Button variant="subtle" @click="customerDialog = true">
              <template #prefix>
                <LucideSquarePen class="size-4" aria-hidden="true" />
              </template>
              {{ __("Edit") }}
            </Button>
            <Dropdown :options="dropdownActions" placement="right">
              <Button variant="subtle" :aria-label="__('More actions')">
                <template #icon>
                  <LucideEllipsis class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </Dropdown>
          </template>
        </template>
      </PageInfo>

      <p
        v-if="
          connection?.connection_status === 'Error' && connection.last_error
        "
        class="mx-5 flex items-start gap-2 rounded-lg border border-outline-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
        role="status"
      >
        <LucideCircleX
          class="mt-0.5 size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <span class="min-w-0 break-words">
          {{ __("ERP connection error: {0}", connection.last_error) }}
        </span>
      </p>

      <div class="flex flex-1 flex-col overflow-y-auto overscroll-y-contain">
        <TicketStats dt="HD Customer" :dn="customer.doc.name" />
        <Tabs
          v-model="activeTab"
          :tabs="tabs"
          class="tabs-sticky-header [&_[role='tablist']]:!bg-surface-base"
        >
          <template #tab-item="{ tab, selected }">
            <button
              class="flex shrink-0 items-center gap-2 whitespace-nowrap border-b border-transparent py-2 text-base transition-colors hover:text-ink-gray-9"
              :class="selected ? 'text-ink-gray-9' : 'text-ink-gray-5'"
            >
              <component
                :is="tab.icon"
                v-if="tab.icon"
                class="size-4"
                aria-hidden="true"
              />
              {{ tab.label }}
              <span
                v-if="tab.count !== undefined"
                class="rounded px-1 font-mono text-xs tabular-nums"
                :class="
                  selected
                    ? 'bg-surface-gray-3 text-ink-gray-8'
                    : 'text-ink-gray-5'
                "
              >
                {{ tab.count }}
              </span>
            </button>
          </template>
          <template #tab-panel="{ tab }">
            <div class="flex min-h-0 flex-1 flex-col p-5">
              <TicketsTab
                v-if="tab.hash === 'tickets'"
                :tickets-list-resource="ticketsListResource"
                :tickets-count-resource="ticketsCountResource"
                :base-filter="{ customer: props.id }"
                :additional-filter="contactFilter"
              />
              <CustomerContactTab v-else-if="tab.hash === 'contacts'" />
              <CustomerProjectsTab
                v-else-if="tab.hash === 'projects'"
                :projects="projects"
                :total="projectCount.data ?? undefined"
              />
              <CustomerSupportHoursTab
                v-else-if="tab.hash === 'support-hours'"
                :customer="props.id"
              />
              <CustomerHealthTab
                v-else-if="tab.hash === 'health'"
                :customer="props.id"
                :health="health.data ?? null"
                :loading="health.loading"
                :error="health.error"
                @retry="health.reload()"
              />
            </div>
          </template>
        </Tabs>
      </div>
    </div>
  </div>
  <EditCustomerDialog
    v-if="customerDialog"
    v-model="customerDialog"
    :id="id"
    @update="customerDialog = false"
  />
  <DeleteWithTicketsDialog
    v-model="showDeleteDialog"
    :name="id"
    link-field="customer"
    :title="__('Delete customer')"
    :message="
      __(
        'Are you sure you want to delete this customer? The reference to this customer will be removed from all the related tickets.'
      )
    "
    :on-delete="handleDelete"
  />
</template>

<script setup lang="ts">
import CustomerContactTab from "@/components/customer/CustomerContactTab.vue";
import CustomerHealthTab from "@/components/customer/CustomerHealthTab.vue";
import CustomerProjectsTab from "@/components/customer/CustomerProjectsTab.vue";
import CustomerSupportHoursTab from "@/components/customer/CustomerSupportHoursTab.vue";
import EditCustomerDialog from "@/components/customer/EditCustomerDialog.vue";
import TicketsTab from "@/components/customer/TicketsTab.vue";
import TicketStats from "@/components/customer/TicketStats.vue";
import DeleteWithTicketsDialog from "@/components/DeleteWithTicketsDialog.vue";
import TicketHashIcon from "@/components/icons/TicketHashIcon.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import PageInfo from "@/components/PageInfo.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { connectionBadge, useCustomer } from "@/composables/customer";
import { healthBadge, type CustomerHealth } from "@/composables/customerHealth";
import { __ } from "@/translation";
import { CustomerResourceSymbol } from "@/types";
import { errorText, hasPermission } from "@/utils";
import {
  Breadcrumbs,
  Button,
  createListResource,
  createResource,
  dayjs,
  Dropdown,
  Tabs,
  usePageMeta,
} from "frappe-ui";
import { computed, h, markRaw, onMounted, provide, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideGlobe from "~icons/lucide/globe";
import LucideHeartPulse from "~icons/lucide/heart-pulse";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideMail from "~icons/lucide/mail";
import LucideMapPin from "~icons/lucide/map-pin";
import LucidePhone from "~icons/lucide/phone";
import LucideSquarePen from "~icons/lucide/square-pen";
import LucideSquareUser from "~icons/lucide/square-user";
import LucideTrash2 from "~icons/lucide/trash-2";
import { getTicketListResource } from "../../stores/docTickets";

const props = defineProps<{
  id: string;
}>();
const route = useRoute();
const router = useRouter();

const { ticketsListResource, ticketsCountResource } = getTicketListResource();
const { doc: customer, handleDelete } = useCustomer(props.id);
provide(CustomerResourceSymbol, customer);

// the customer's projects the viewer may see, the latest PROJECT_LIMIT of them;
// the tab orders them and says when there are more
const PROJECT_LIMIT = 100;
const projects = createListResource({
  doctype: "Project",
  filters: { customer: props.id },
  fields: [
    "name",
    "project_name",
    "status",
    "expected_end_date",
    "project_lead",
  ],
  orderBy: "modified desc",
  pageLength: PROJECT_LIMIT,
  auto: true,
});
// the real total, permission-aware like the list
const projectCount = createResource({
  url: "frappe.desk.reportview.get_count",
  makeParams: () => ({ doctype: "Project", filters: { customer: props.id } }),
  auto: true,
});

// the customer's ERP site connection, if it has one
const connections = createListResource({
  doctype: "HDS Support Connection",
  filters: { customer_name: props.id },
  fields: [
    "name",
    "connection_status",
    "site_url",
    "last_health_check",
    "last_error",
  ],
  orderBy: "modified desc",
  pageLength: 1,
  auto: true,
});
const connection = computed(() => connections.data?.[0] ?? null);

// the header badge and the Health tab (docs/customer-health.md)
const health = createResource({
  url: "helpdesk.api.customer_health.get_customer_health",
  method: "GET",
  makeParams: () => ({ customer: props.id }),
  auto: true,
});

const tabs = computed(() => [
  {
    label: __("Tickets"),
    hash: "tickets",
    count: ticketsCountResource.data ?? 0,
    icon: h(TicketHashIcon, { class: "size-4" }),
  },
  {
    label: __("Contacts"),
    hash: "contacts",
    count: customer.getContacts.loading
      ? 0
      : customer.getContacts.data?.length ?? 0,
    icon: markRaw(LucideSquareUser),
  },
  {
    label: __("Projects"),
    hash: "projects",
    count:
      projectCount.data ??
      (projects.data && projects.hasNextPage
        ? `${PROJECT_LIMIT}+`
        : projects.data?.length ?? 0),
    icon: markRaw(LucideFolderKanban),
  },
  {
    label: __("Support hours"),
    hash: "support-hours",
    count: undefined,
    icon: markRaw(LucideHourglass),
  },
  {
    label: __("Health"),
    hash: "health",
    count: undefined,
    icon: markRaw(LucideHeartPulse),
  },
]);

const contactFilter = computed(() => {
  const contacts = customer.getContacts.data ?? [];
  if (contacts.length <= 1) return undefined;
  return {
    key: "contact",
    placeholder: __("Contact"),
    doctype: "Contact",
    filters: {
      name: [
        "in",
        contacts.map((c: { contact_name: string }) => c.contact_name),
      ],
    },
  };
});

const activeTab = computed<number>({
  get() {
    const index = tabs.value.findIndex((t) => t.hash === route.hash.slice(1));
    if (index === -1) {
      router.replace({ hash: "" });
      return 0;
    }
    return index;
  },
  set(i) {
    router.replace({ hash: i === 0 ? "" : `#${tabs.value[i].hash}` });
  },
});

const breadcrumbs = [
  { label: __("Customers"), route: { name: "CustomerList" } },
  { label: props.id },
];

const customerDialog = ref(false);
const showDeleteDialog = ref(false);

const dropdownActions = computed(() => [
  {
    group: __("Danger"),
    hideLabel: true,
    items: [
      {
        label: __("Delete customer"),
        icon: LucideTrash2,
        theme: "red",
        onClick: () => {
          showDeleteDialog.value = true;
        },
      },
    ],
  },
]);

function hostOf(url: string | null) {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

const connectionInfo = computed(() => {
  const conn = connection.value;
  if (!conn) return null;
  const checked = conn.last_health_check
    ? __("checked {0}", dayjs(conn.last_health_check).fromNow())
    : __("not checked yet");
  return markRaw(
    h("span", { class: "flex min-w-0 items-center gap-1.5" }, [
      h("span", { class: "sr-only" }, __("ERP connection:")),
      h(TaskyBadge, {
        ...connectionBadge({
          status: conn.connection_status,
          site_url: conn.site_url,
        }),
        title: __("ERP connection"),
      }),
      h(
        "span",
        { class: "truncate", title: conn.site_url || undefined },
        [hostOf(conn.site_url), checked].filter(Boolean).join(" · ")
      ),
    ])
  );
});

// the status links to the Health tab, which says why
const healthInfo = computed(() => {
  const data = health.data as CustomerHealth | null | undefined;
  if (!data) return null;
  const badge = healthBadge(data.status);
  return markRaw(
    h(
      RouterLink,
      {
        to: { hash: "#health" },
        class:
          "rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4",
        "aria-label": __("Health: {0}. See why", badge.label),
      },
      () => h(TaskyBadge, badge)
    )
  );
});

const customerInfo = computed(() => [
  {
    component: healthInfo.value,
    condition: !!healthInfo.value,
  },
  {
    icon: markRaw(LucideGlobe),
    value: customer.doc.domain,
    condition: !!customer.doc.domain,
  },
  {
    icon: markRaw(LucideMail),
    value: customer.doc.email_id,
    condition: !!customer.doc.email_id,
  },
  {
    icon: markRaw(LucidePhone),
    value: customer.doc.mobile_no,
    condition: !!customer.doc.mobile_no,
  },
  {
    icon: markRaw(LucideMapPin),
    value: customer.doc.country,
    condition: !!customer.doc.country,
  },
  {
    component: connectionInfo.value,
    condition: !!connectionInfo.value,
  },
]);

onMounted(() => {
  if (hasPermission()) {
    customer.getPendingInvites.fetch();
  }
  customer.getContacts.fetch();
  ticketsListResource.update({
    filters: {
      customer: props.id,
    },
  });
  ticketsListResource.fetch();
  ticketsCountResource.fetch();
});

usePageMeta(() => ({ title: __("Customer: {0}", props.id) }));
</script>

<style scoped>
/* frappe-ui's TabsRoot clips with overflow-hidden, which traps the sticky
   tablist. Let it overflow so the tablist sticks to the page scroll container. */
.tabs-sticky-header {
  overflow: visible !important;
}
/* Same for the tab panels, so sticky children (e.g. the ticket filter bar)
   can stick to the page scroll container instead of being clipped. */
.tabs-sticky-header :deep([role="tabpanel"]) {
  overflow: visible !important;
}
.tabs-sticky-header :deep([role="tablist"]) {
  position: sticky;
  top: 0;
  z-index: 10;
}
</style>
