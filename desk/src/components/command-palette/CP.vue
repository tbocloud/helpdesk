<template>
  <Dialog v-model:open="show" size="xl" position="top" bare>
    <template #default>
      <div>
        <Combobox nullable @update:model-value="onSelection">
          <div class="relative">
            <div class="pl-4.5 absolute inset-y-0 left-0 flex items-center">
              <LucideSearch class="h-4 w-4 text-ink-gray-6" />
            </div>
            <ComboboxInput
              :placeholder="placeholder"
              class="pl-11.5 pr-4.5 w-full border-none bg-transparent py-3 text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:ring-0"
              autocomplete="off"
              @input="onInput"
            />
          </div>
          <ComboboxOptions
            class="max-h-96 overflow-auto border-t border-outline-gray-1"
            static
            :hold="true"
          >
            <div
              v-for="group in groups"
              :key="group.title"
              class="mt-4.5 mb-2 first:mt-3"
            >
              <div
                v-if="!group.hideTitle"
                class="px-4.5 mb-2.5 text-base text-ink-gray-5"
              >
                {{ group.title }}
              </div>
              <ComboboxOption
                v-for="item in group.items"
                :key="item.key"
                v-slot="{ active }"
                :value="item"
                class="px-2.5"
              >
                <CPGroup :item="item" :active="active" />
              </ComboboxOption>
            </div>
            <p
              v-if="statusText"
              class="px-4.5 py-4 text-p-sm text-ink-gray-5"
              role="status"
            >
              {{ statusText }}
            </p>
          </ComboboxOptions>
        </Combobox>
      </div>
    </template>
  </Dialog>
</template>
<script setup lang="ts">
import { useShortcut } from "@/composables/shortcuts";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { isCustomerPortal } from "@/utils";
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from "@headlessui/vue";
import { watchDebounced } from "@vueuse/core";
import { createResource, Dialog } from "frappe-ui";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { Component } from "vue";
import type { RouteLocationRaw } from "vue-router";
import { useRouter } from "vue-router";

import LucideFileSearch from "~icons/lucide/file-search";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTicket from "~icons/lucide/ticket";
import CPGroup from "./CPGroup.vue";
import type { NavArea } from "../layouts/navigation";

interface PaletteItem {
  key: string;
  title: string;
  description?: string;
  icon?: Component;
  route: RouteLocationRaw;
}

interface PaletteGroup {
  title: string;
  hideTitle?: boolean;
  items: PaletteItem[];
}

// the sidebar's pages, already filtered to what this person may open
const props = defineProps<{ areas: NavArea[] }>();

const router = useRouter();
const authStore = useAuthStore();

const show = defineModel<boolean>({ default: false });
const query = ref("");
const term = computed(() => query.value.trim());
const MIN_SEARCH = 2;

const placeholder = computed(() =>
  authStore.canWorkTickets
    ? __("Search pages, tasks, projects, or #234 for a ticket")
    : __("Search pages, tasks and projects")
);

const pages = computed<PaletteItem[]>(() => {
  const seen = new Set<string>();
  const out: PaletteItem[] = [];
  for (const area of props.areas)
    for (const group of area.groups)
      for (const item of group.items) {
        if (seen.has(item.id)) continue;
        seen.add(item.id);
        out.push({
          key: `page:${item.id}`,
          title: item.label,
          description: area.label !== item.label ? area.label : undefined,
          icon: item.icon,
          route: { name: item.to, query: item.query },
        });
      }
  return out;
});

const matchingPages = computed(() => {
  const q = term.value.toLowerCase();
  if (!q) return pages.value;
  return pages.value.filter(
    (p) =>
      p.title.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q)
  );
});

const work = createResource({
  url: "helpdesk.tasky.api.search_work",
});

watchDebounced(
  term,
  (q) => {
    if (q.length >= MIN_SEARCH && !q.startsWith("#")) work.submit({ query: q });
  },
  { debounce: 250 }
);

// a slower, older answer must not show under a newer query
const workResults = computed(() =>
  work.params?.query === term.value && work.data
    ? work.data
    : { tasks: [], projects: [] }
);
const searching = computed(
  () =>
    term.value.length >= MIN_SEARCH &&
    !term.value.startsWith("#") &&
    (work.loading || work.params?.query !== term.value)
);

const groups = computed<PaletteGroup[]>(() => {
  const q = term.value;
  const out: PaletteGroup[] = [];

  if (q.startsWith("#")) {
    const id = q.slice(1).trim();
    if (id)
      out.push({
        title: __("Ticket"),
        hideTitle: true,
        items: [
          {
            key: `ticket:${id}`,
            title: __("Go to ticket #{0}", [id]),
            icon: LucideTicket,
            route: { name: "TicketAgent", params: { ticketId: id } },
          },
        ],
      });
    return out;
  }

  if (matchingPages.value.length)
    out.push({ title: __("Pages"), items: matchingPages.value });

  const { tasks, projects } = workResults.value;
  if (projects.length)
    out.push({
      title: __("Projects"),
      items: projects.map((p: any) => ({
        key: `project:${p.name}`,
        title: p.project_name || p.name,
        description: p.status,
        icon: LucideFolderKanban,
        route: { name: "TaskyProject", params: { projectId: p.name } },
      })),
    });
  if (tasks.length)
    out.push({
      title: __("Tasks"),
      items: tasks.map((t: any) => ({
        key: `task:${t.name}`,
        title: t.subject || t.name,
        description: [t.project_name, t.status].filter(Boolean).join(" · "),
        icon: LucideSquareCheck,
        route: { name: "MyWork", query: { task: t.name } },
      })),
    });

  // the full-text search page covers tickets, emails and comments
  if (q.length >= MIN_SEARCH && authStore.canWorkTickets)
    out.push({
      title: __("Tickets"),
      items: [
        {
          key: "search:tickets",
          title: __('Search tickets for "{0}"', [q]),
          icon: LucideFileSearch,
          route: { name: "SearchAgent", query: { q } },
        },
      ],
    });

  return out;
});

const statusText = computed(() => {
  if (searching.value) return __("Searching tasks and projects…");
  if (!groups.value.length) return __("Nothing matches “{0}”.", [term.value]);
  return "";
});

function onInput(e: Event) {
  query.value = (e.target as HTMLInputElement).value;
}

function onSelection(item: PaletteItem | null) {
  if (!item) return;
  router.push(item.route);
  show.value = false;
}

watch(show, (open) => {
  if (open) query.value = "";
});

onMounted(() => {
  if (isCustomerPortal.value) return;
  useShortcut({ key: "k", meta: true }, () => (show.value = !show.value));
});

onBeforeUnmount(() => {
  show.value = false;
});
</script>
