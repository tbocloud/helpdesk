<template>
  <div class="flex flex-col">
    <!-- Filter bar: sticks below the tablist while the page scrolls -->
    <div
      class="sticky top-[46px] z-[5] -mt-5 flex items-center justify-between gap-3 bg-surface-base pt-5 pb-3"
    >
      <FormControl
        v-model="search"
        :placeholder="__('Search by ID or subject')"
        :aria-label="__('Search tickets')"
        class="w-full md:w-56"
      >
        <template #prefix>
          <LucideSearch class="size-4 text-ink-gray-5" aria-hidden="true" />
        </template>
      </FormControl>

      <div class="flex items-center gap-2" v-if="!isMobileView">
        <Link
          class="w-48"
          v-for="filter in filterFields"
          :key="filter.key"
          v-model="filters[filter.key]"
          :placeholder="filter.placeholder"
          :doctype="filter.doctype"
          :filters="filter.filters"
        />
      </div>
    </div>

    <!-- Table -->
    <div class="flex min-h-0 flex-1 flex-col">
      <!-- Loading -->
      <template
        v-if="ticketsListResource.loading && !ticketsListResource.data?.length"
      >
        <div
          class="py-16 text-center text-sm text-ink-gray-4 flex items-center justify-center"
        >
          <LoadingIndicator :scale="10" />
        </div>
      </template>
      <TaskyState
        v-else-if="ticketsListResource.error && !ticketsListResource.data"
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the tickets')"
        :message="errorText(ticketsListResource.error, __('Try again.'))"
        error
      >
        <Button :label="__('Retry')" @click="ticketsListResource.reload()" />
      </TaskyState>
      <TaskyState
        v-else-if="!ticketsListResource.data?.length && isFiltered"
        :icon="LucideSearchX"
        :title="__('No tickets match these filters')"
        :message="__('Try another search, or clear the filters.')"
      >
        <Button :label="__('Clear filters')" @click="clearFilters" />
      </TaskyState>
      <TaskyState
        v-else-if="!ticketsListResource.data?.length"
        :icon="LucideTicket"
        :title="__('No tickets yet')"
        :message="__('Tickets raised by or for them show up here.')"
      />
      <!-- Main Content -->
      <template v-else>
        <!-- Headers -->
        <!-- top-[106px] = tablist (46) + filter bar (60); remeasure
             if either changes -->
        <div
          class="sticky top-[106px] z-[5] grid items-center border-b bg-surface-base px-1 py-2 text-xs-medium text-ink-gray-5"
          :style="gridTemplateStyle"
        >
          <component
            :is="col.sortable ? NativeButton : 'div'"
            v-for="col in columns"
            :key="col.key"
            v-bind="col.sortable ? { type: 'button' } : {}"
            class="group flex select-none items-center gap-1 rounded text-left text-ink-gray-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :class="col.sortable ? 'hover:text-ink-gray-8' : ''"
            :aria-label="
              col.sortable ? __('Sort by {0}', col.label) : undefined
            "
            @click="handleSortClick(col)"
          >
            {{ col.label }}
            <LucideArrowUpDown
              v-if="col.sortable"
              class="size-3 transition-opacity"
              :class="
                sort.field === col.key
                  ? 'text-ink-gray-7 opacity-100'
                  : 'opacity-0 group-hover:opacity-60 group-focus-visible:opacity-60'
              "
              aria-hidden="true"
            />
          </component>
        </div>
        <!-- Rows -->
        <div class="pb-6" :class="isMobileView ? '' : 'overflow-x-hidden'">
          <template
            v-for="(ticket, i) in ticketsListResource.data"
            :key="ticket.name"
          >
            <!-- opens in a new tab, so this page stays put -->
            <RouterLink
              :to="{
                name: 'TicketAgent',
                params: { ticketId: String(ticket.name) },
              }"
              target="_blank"
              class="grid items-center rounded px-1 py-3 text-sm text-ink-gray-8 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
              :style="gridTemplateStyle"
            >
              <!-- ID -->
              <div class="font-mono tabular-nums text-ink-gray-6">
                {{ ticket.name }}
              </div>

              <!-- Subject -->
              <div class="truncate font-medium max-w-[90%]">
                {{ ticket.subject }}
              </div>

              <!-- Status -->
              <div class="flex items-center gap-1.5">
                <IndicatorIcon
                  :class="getStatus(ticket.status)?.parsed_color"
                />
                <span>{{ ticket.status }}</span>
              </div>

              <!-- Priority -->
              <div v-if="!isMobileView" class="flex items-center gap-1.5">
                <span>{{ ticket.priority }}</span>
              </div>

              <!-- First Response -->
              <div v-if="!isMobileView" class="text-ink-gray-6">
                {{ dayjsLocal(ticket.response_by).fromNow() }}
              </div>

              <!-- Resolution -->
              <div v-if="!isMobileView" class="text-ink-gray-6">
                {{ dayjsLocal(ticket.resolution_by).fromNow() }}
              </div>

              <!-- Assigned To -->
              <div
                v-if="!isMobileView"
                class="flex items-center gap-2 assigned-cell"
              >
                <MultipleAvatar :avatars="ticket._assign" size="xs" />
              </div>
            </RouterLink>
            <hr class="mx-1" v-if="i !== ticketRowsCount - 1" />
          </template>
          <!-- Load More -->
          <div
            class="flex justify-center py-6"
            v-if="ticketsListResource.hasNextPage"
          >
            <Button
              :loading="ticketsListResource.loading"
              :label="__('Load More')"
              icon-left="refresh-cw"
              @click="
                () => {
                  ticketsListResource.next();
                }
              "
            />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import Link from "@/components/frappe-ui/Link.vue";
import { IndicatorIcon } from "@/components/icons";
import { useScreenSize } from "@/composables/screen";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { __ } from "@/translation";
import type { ListResource, Resource } from "@/types";
import type { HDTicket } from "@/types/doctypes";
import { watchDebounced } from "@vueuse/core";
import TaskyState from "@/components/TaskyState.vue";
import { errorText } from "@/utils";
import { Button, dayjsLocal, FormControl, LoadingIndicator } from "frappe-ui";
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { RouterLink } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import LucideTicket from "~icons/lucide/ticket";
import MultipleAvatar from "../MultipleAvatar.vue";

type TicketFilterField = {
  key: string;
  placeholder: string;
  doctype: string;
  filters?: Record<string, any>;
};

const props = defineProps<{
  ticketsListResource: ListResource<HDTicket>;
  ticketsCountResource: Resource<number>;
  baseFilter: Record<string, string>;
  additionalFilter?: TicketFilterField;
}>();

const { ticketsListResource, ticketsCountResource, baseFilter } = props;

const { isMobileView } = useScreenSize();

const search = ref("");
const sort = reactive<{ field: string | null; order: "asc" | "desc" }>({
  field: null,
  order: "asc",
});
const filters = reactive<Record<string, string>>({
  status: "",
  priority: "",
});

const gridTemplateStyle = computed(() =>
  isMobileView.value
    ? "grid-template-columns: 5rem 1fr 7rem"
    : "grid-template-columns: 6rem 1fr 8rem 7rem 8rem 8rem 9rem"
);

type Column = {
  key: string;
  label: string;
  sortable: boolean;
  desktopOnly?: boolean;
};
const allColumns: Column[] = [
  { key: "name", label: __("Ticket ID"), sortable: true },
  { key: "subject", label: __("Subject"), sortable: true },
  { key: "status", label: __("Status"), sortable: true },
  { key: "priority", label: __("Priority"), sortable: true, desktopOnly: true },
  {
    key: "response_by",
    label: __("First Response"),
    sortable: true,
    desktopOnly: true,
  },
  {
    key: "resolution_by",
    label: __("Resolution"),
    sortable: true,
    desktopOnly: true,
  },
  {
    key: "_assign",
    label: __("Assigned To"),
    sortable: false,
    desktopOnly: true,
  },
];
const columns = computed(() =>
  isMobileView.value ? allColumns.filter((c) => !c.desktopOnly) : allColumns
);

const filterFields = computed(() => {
  const base: TicketFilterField[] = [
    {
      key: "status",
      placeholder: __("Status"),
      doctype: "HD Ticket Status",
    },
    {
      key: "priority",
      placeholder: __("Priority"),
      doctype: "HD Ticket Priority",
    },
  ];
  if (props.additionalFilter) {
    base.push(props.additionalFilter);
  }
  return base;
});

function handleSortClick(column: Column) {
  if (!column.sortable) return;
  if (sort.field === column.key) {
    sort.order = sort.order === "asc" ? "desc" : "asc";
  } else {
    sort.field = column.key;
    sort.order = "desc";
  }
}

const ticketRowsCount = computed(() => ticketsListResource.data?.length ?? 0);

const { getStatus } = useTicketStatusStore();

const isFiltered = computed(
  () => !!search.value.trim() || Object.values(filters).some(Boolean)
);

function clearFilters() {
  search.value = "";
  for (const key of Object.keys(filters)) filters[key] = "";
}

watchDebounced(
  [search, () => sort.field, () => sort.order, () => ({ ...filters })],
  () => {
    ticketsListResource.update({
      filters: {
        ...baseFilter,
        status: filters.status || undefined,
        priority: filters.priority || undefined,
        ...(props.additionalFilter
          ? {
              [props.additionalFilter.key]:
                filters[props.additionalFilter.key] || undefined,
            }
          : {}),
      },
      orderBy: sort.field ? `${sort.field} ${sort.order}` : undefined,
      orFilters: search.value
        ? {
            subject: ["like", `%${search.value}%`],
            name: ["like", `%${search.value}%`],
          }
        : undefined,
    });
    ticketsListResource.reload();
    ticketsCountResource.fetch();
  },
  { debounce: 300 }
);

onBeforeUnmount(() => {
  ticketsListResource.update({
    filters: { ...baseFilter },
    orFilters: {},
  });
  ticketsListResource.reload();
  ticketsCountResource.fetch();
});
</script>

<style scoped>
.assigned-cell :deep(.truncate) {
  @apply text-sm text-ink-gray-6;
}
</style>
