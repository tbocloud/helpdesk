<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">{{ __("Contacts") }}</h1>
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
          :label="__('New contact')"
          @click="showNewContactModal = true"
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
                "The people who raise tickets, and the customers they belong to. Invite them to the portal from their page."
              )
            }}
          </p>
          <div class="flex gap-2">
            <TextInput
              v-model="search"
              type="search"
              class="min-w-0 flex-1 sm:w-64 sm:flex-none"
              :placeholder="__('Search name, email or phone')"
              :aria-label="__('Search contacts')"
            >
              <template #prefix>
                <LucideSearch
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </template>
            </TextInput>
            <FormControl
              v-model="sort"
              type="select"
              class="w-36 shrink-0"
              :options="DIRECTORY_SORTS"
              :aria-label="__('Sort contacts')"
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
          :row-to="(row) => ({ name: 'Contact', params: { id: row.name } })"
          :row-label="(row) => String(row.full_name || row.name)"
          :error-title="__('Couldn\'t load contacts')"
          :deletable="hasPermission()"
          doctype="Contact"
          :noun="__('contacts')"
          @more="more"
          @retry="reload"
          @deleted="reload"
        >
          <template #row="{ row }">
            <div class="flex min-w-0 items-center gap-3">
              <Avatar
                size="lg"
                shape="circle"
                :label="String(row.full_name || row.name)"
                :image="(row.image as string) || undefined"
              />
              <div class="min-w-0">
                <div class="truncate text-sm text-ink-gray-9">
                  {{ row.full_name || row.name }}
                </div>
                <div
                  class="flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
                >
                  <span v-if="row.email_id" class="truncate font-mono">
                    {{ row.email_id }}
                  </span>
                  <span
                    v-else-if="row.mobile_no"
                    class="truncate font-mono tabular-nums"
                  >
                    {{ row.mobile_no }}
                  </span>
                  <!-- on small screens the customer and count fold into this line -->
                  <template v-if="customerLabel(row)">
                    <span class="md:hidden" aria-hidden="true">·</span>
                    <span class="truncate md:hidden">
                      {{ customerLabel(row) }}
                    </span>
                  </template>
                  <template v-if="row.open_tickets">
                    <span class="md:hidden" aria-hidden="true">·</span>
                    <span class="tabular-nums md:hidden">
                      {{ openTicketsLabel(row.open_tickets as number) }}
                    </span>
                  </template>
                </div>
              </div>
            </div>
            <span
              class="hidden truncate text-sm md:block"
              :class="
                customerLabel(row) ? 'text-ink-gray-8' : 'text-ink-gray-4'
              "
              :title="(row.customers as string[]).join(', ')"
            >
              {{ customerLabel(row) || __("None") }}
            </span>
            <span
              class="hidden text-right font-mono text-sm tabular-nums md:block"
              :class="row.open_tickets ? 'text-ink-gray-8' : 'text-ink-gray-4'"
            >
              {{ row.open_tickets }}
            </span>
            <span class="flex justify-end md:justify-start">
              <TaskyBadge
                v-if="row.portal"
                v-bind="PORTAL_BADGE[row.portal as PortalStatus]"
              />
              <span v-else class="hidden text-sm text-ink-gray-4 md:inline">
                {{ __("No access") }}
              </span>
            </span>
          </template>

          <template #empty>
            <TaskyState
              v-if="searching"
              :icon="LucideSearchX"
              :title="__('No contacts match “{0}”', search.trim())"
              :message="
                __('Check the spelling, or search by email or phone number.')
              "
            >
              <Button :label="__('Clear search')" @click="search = ''" />
            </TaskyState>
            <TaskyState
              v-else
              :icon="LucideContact"
              :title="__('No contacts yet')"
              :message="
                __(
                  'Contacts are added when customers email in, or you can add one and link it to a customer.'
                )
              "
            >
              <Button
                variant="solid"
                :label="__('New contact')"
                @click="showNewContactModal = true"
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
    <NewContactDialog v-model="showNewContactModal" />
  </div>
</template>

<script setup lang="ts">
import DirectoryList, {
  type DirectoryColumn,
} from "@/components/DirectoryList.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import NewContactDialog from "@/components/contact/NewContactDialog.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { PORTAL_BADGE, type PortalStatus } from "@/composables/contact";
import {
  DIRECTORY_SORTS,
  openTicketsLabel,
  useDirectory,
} from "@/composables/directory";
import { hasPermission } from "@/utils";
import { __ } from "@/translation";
import { Avatar, Button, FormControl, TextInput, usePageMeta } from "frappe-ui";
import LucideContact from "~icons/lucide/contact";
import LucidePlus from "~icons/lucide/plus";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import { showNewContactModal } from "./dialogState";

interface ContactRow {
  name: string;
  full_name: string | null;
  email_id: string | null;
  mobile_no: string | null;
  image: string | null;
  user: string | null;
  customers: string[];
  open_tickets: number;
  portal: PortalStatus | null;
}

const COLUMNS: DirectoryColumn[] = [
  { key: "contact", label: __("Contact") },
  { key: "customers", label: __("Customer") },
  { key: "open_tickets", label: __("Open tickets"), align: "right" },
  { key: "portal", label: __("Portal") },
];
const GRID =
  "grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1fr)_minmax(0,14rem)_7rem_9rem]";

const {
  search,
  sort,
  rows,
  total,
  hasMore,
  loading,
  error,
  searching,
  reload,
  more,
} = useDirectory<ContactRow>("helpdesk.api.directory.get_contact_directory");

function customerLabel(row: { customers?: unknown }) {
  const customers = (row.customers as string[]) ?? [];
  if (customers.length <= 1) return customers[0] ?? "";
  return __("{0} +{1} more", customers[0], String(customers.length - 1));
}

usePageMeta(() => ({ title: __("Contacts") }));
</script>
