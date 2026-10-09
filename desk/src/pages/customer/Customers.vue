<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("Customers") }}</h1>
        <span
          v-if="total !== undefined"
          class="font-mono text-sm tabular-nums text-ink-gray-5"
        >
          {{ total }}
        </span>
      </template>
      <template #right-header>
        <Button
          variant="solid"
          :label="__('New customer')"
          @click="showNewCustomer = true"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div
          class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <p class="max-w-xl text-p-sm text-ink-gray-6">
            {{
              __(
                "The companies and people you support, and how each one is doing. Open one for its tickets, contacts, projects and health."
              )
            }}
          </p>
          <div class="flex flex-wrap gap-2">
            <TextInput
              v-model="search"
              type="search"
              class="min-w-0 basis-full sm:w-64 sm:basis-auto"
              :placeholder="__('Search name or domain')"
              :aria-label="__('Search customers')"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </TextInput>
            <FormControl
              v-model="health"
              type="select"
              class="min-w-0 flex-1 sm:w-40 sm:flex-none"
              :options="HEALTH_FILTERS"
              :aria-label="__('Filter by health')"
            />
            <FormControl
              v-model="sort"
              type="select"
              class="min-w-0 flex-1 sm:w-44 sm:flex-none"
              :options="CUSTOMER_SORTS"
              :aria-label="__('Sort customers')"
            />
          </div>
        </div>

        <DirectoryList
          class="mt-4"
          :columns="COLUMNS"
          :grid-class="GRID"
          :rows="rows"
          :total="total"
          :loading="loading"
          :error="error"
          :has-more="hasMore"
          :row-to="(row) => ({ name: 'Customer', params: { id: row.name } })"
          :row-label="(row) => String(row.customer_name || row.name)"
          :error-title="__('Couldn\'t load customers')"
          :deletable="hasPermission()"
          doctype="HD Customer"
          :noun="__('customers')"
          @more="more"
          @retry="reload"
          @deleted="reload"
        >
          <template #row="{ row }">
            <div class="flex min-w-0 items-center gap-3">
              <Avatar
                size="lg"
                shape="square"
                :label="String(row.customer_name || row.name)"
                :image="(row.image as string) || undefined"
              />
              <div class="min-w-0">
                <div class="truncate text-sm text-ink-gray-9">
                  {{ row.customer_name || row.name }}
                </div>
                <div
                  class="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
                >
                  <span v-if="row.domain" class="truncate">
                    {{ row.domain }}
                  </span>
                  <!-- on small screens the count columns fold into this line -->
                  <span v-if="row.domain" class="md:hidden" aria-hidden="true"
                    >·</span
                  >
                  <span class="tabular-nums md:hidden">
                    {{ openTicketsLabel(row.open_tickets as number) }}
                  </span>
                  <span
                    v-if="row.active_projects"
                    class="md:hidden"
                    aria-hidden="true"
                    >·</span
                  >
                  <span
                    v-if="row.active_projects"
                    class="tabular-nums md:hidden"
                  >
                    {{ projectsLabel(row.active_projects as number) }}
                  </span>
                </div>
              </div>
            </div>
            <span class="flex min-w-0 flex-col items-end gap-1 md:items-start">
              <TaskyBadge
                v-if="row.health"
                v-bind="healthBadge((row.health as HealthBrief).status)"
              />
              <span v-else class="text-sm text-ink-gray-4">-</span>
              <span
                v-if="(row.health as HealthBrief | null)?.reasons.length"
                class="hidden w-full truncate text-xs text-ink-gray-5 md:block"
                :title="(row.health as HealthBrief).reasons.join(', ')"
              >
                {{ (row.health as HealthBrief).reasons.join(", ") }}
              </span>
              <!-- phones: the connection only when it's failing -->
              <TaskyBadge
                v-if="failing(row.connection as Connection | null)"
                class="md:hidden"
                v-bind="connectionBadge(row.connection as Connection)"
              />
            </span>
            <span
              class="hidden text-right font-mono text-sm tabular-nums md:block"
              :class="row.open_tickets ? 'text-ink-gray-8' : 'text-ink-gray-4'"
            >
              {{ row.open_tickets }}
            </span>
            <span
              class="hidden text-right font-mono text-sm tabular-nums md:block"
              :class="
                row.active_projects ? 'text-ink-gray-8' : 'text-ink-gray-4'
              "
            >
              {{ row.active_projects }}
            </span>
            <span class="hidden md:flex">
              <TaskyBadge
                v-if="row.connection"
                v-bind="connectionBadge(row.connection as Connection)"
              />
              <span v-else class="text-sm text-ink-gray-4">
                {{ __("None") }}
              </span>
            </span>
          </template>

          <template #empty>
            <TaskyState
              v-if="searching"
              :icon="LucideSearchX"
              :title="__('No customers match “{0}”', search.trim())"
              :message="__('Check the spelling, or search by their domain.')"
            >
              <Button :label="__('Clear search')" @click="search = ''" />
            </TaskyState>
            <TaskyState
              v-else-if="health"
              :icon="LucideSearchX"
              :title="__('No customers with this health')"
              :message="
                __(
                  'Health is worked out every few minutes from tickets, project work, support hours, sign-offs and the ERP connection.'
                )
              "
            >
              <Button :label="__('Show all customers')" @click="health = ''" />
            </TaskyState>
            <TaskyState
              v-else
              :icon="LucideBuilding2"
              :title="__('No customers yet')"
              :message="
                __(
                  'Add the companies you support. Their tickets, contacts and projects are then kept together.'
                )
              "
            >
              <Button
                variant="solid"
                :label="__('New customer')"
                @click="showNewCustomer = true"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </TaskyState>
          </template>
        </DirectoryList>
      </div>
    </div>
    <NewCustomerDialog v-model="showNewCustomer" />
  </div>
</template>

<script setup lang="ts">
import DirectoryList, {
  type DirectoryColumn,
} from "@/components/DirectoryList.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import NewCustomerDialog from "@/components/customer/NewCustomerDialog.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { connectionBadge, type Connection } from "@/composables/customer";
import {
  HEALTH_FILTERS,
  healthBadge,
  type HealthBrief,
} from "@/composables/customerHealth";
import {
  CUSTOMER_SORTS,
  openTicketsLabel,
  useDirectory,
} from "@/composables/directory";
import { hasPermission } from "@/utils";
import { __ } from "@/translation";
import { Avatar, Button, FormControl, TextInput, usePageMeta } from "frappe-ui";
import { ref } from "vue";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucidePlus from "~icons/lucide/plus";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";

interface CustomerRow {
  name: string;
  customer_name: string;
  domain: string | null;
  image: string | null;
  open_tickets: number;
  active_projects: number;
  connection: Connection | null;
  health: HealthBrief | null;
}

const COLUMNS: DirectoryColumn[] = [
  { key: "customer", label: __("Customer") },
  { key: "health", label: __("Health") },
  { key: "open_tickets", label: __("Open tickets"), align: "right" },
  { key: "active_projects", label: __("Active projects"), align: "right" },
  { key: "connection", label: __("ERP connection") },
];
const GRID =
  "grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1fr)_11rem_6rem_6rem_8rem]";

const {
  search,
  sort,
  filter: health,
  rows,
  total,
  hasMore,
  loading,
  error,
  searching,
  reload,
  more,
} = useDirectory<CustomerRow>("helpdesk.api.directory.get_customer_directory", {
  sorts: CUSTOMER_SORTS,
  filterKey: "health",
});
const showNewCustomer = ref(false);

function failing(connection: Connection | null) {
  return (
    connection?.status === "Error" || connection?.status === "Disconnected"
  );
}

function projectsLabel(count: number) {
  return count === 1
    ? __("1 active project")
    : __("{0} active projects", String(count));
}

usePageMeta(() => ({ title: __("Customers") }));
</script>
