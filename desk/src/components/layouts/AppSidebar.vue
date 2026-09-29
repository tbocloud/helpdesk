<template>
  <Sidebar
    v-model:collapsed="collapsed"
    :disable-collapse="mobile"
    class="border-e border-outline-gray-1"
  >
    <div class="flex h-full flex-col p-2">
      <UserMenu :options="profileSettings" :is-collapsed="isCollapsed" />

      <ScrollArea class="mt-2 min-h-0 flex-1 -mx-2" viewport-class="px-2">
        <template v-for="(section, index) in sections" :key="index">
          <template v-if="section.label && !section.collapsible">
            <div
              v-if="!isCollapsed"
              class="select-none px-2.5 pb-1.5 pt-3.5 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
            >
              {{ section.label }}
            </div>
            <div v-else class="mx-2 my-2 border-t border-outline-gray-2" />
          </template>
          <SidebarLabel
            v-else-if="section.label"
            divider
            class="my-1 select-none"
            :class="section.collapsible && !isCollapsed && 'cursor-pointer'"
            @click="section.collapsible && toggleSection(section.label)"
          >
            <span class="flex items-center gap-1.5 text-sm font-medium">
              <span
                class="lucide-chevron-right size-4 shrink-0 text-ink-gray-9 transition-transform duration-300 ease-in-out"
                :class="{ 'rotate-90': isSectionOpen(section.label) }"
              />
              <span class="truncate">{{ section.label }}</span>
            </span>
          </SidebarLabel>
          <nav
            v-if="!section.collapsible || isSectionOpen(section.label)"
            class="flex flex-col gap-0.5"
          >
            <SidebarItem
              v-for="item in section.items"
              :key="item.key"
              :id="item.id"
              :label="__(item.label)"
              :active="item.isActive"
              @click="item.onClick && item.onClick()"
            >
              <template #prefix>
                <span
                  class="tbo-nav-icon relative grid size-4 shrink-0 place-items-center text-ink-gray-6"
                >
                  <component :is="item.icon" class="size-4" />
                  <span
                    v-if="
                      item.key === 'notifications' && item.badge && isCollapsed
                    "
                    class="absolute -right-0.5 -top-0.5 size-1.5 rounded-full bg-surface-blue-5"
                  />
                </span>
              </template>
              <template #suffix>
                <kbd
                  v-if="item.shortcut"
                  class="me-2 flex items-center gap-0.5 rounded border border-outline-gray-2 px-1 text-2xs font-medium text-ink-gray-5"
                >
                  <component :is="device.modifierIcon" class="h-3 w-3" />
                  K
                </kbd>
                <span
                  v-else-if="item.badge"
                  class="me-2 font-mono text-xs tabular-nums text-ink-gray-5"
                  :aria-label="__('{0} unread', String(item.badge))"
                >
                  {{ item.badge > 99 ? "99+" : item.badge }}
                </span>
                <Dropdown
                  v-else-if="item.view"
                  side="right"
                  align="start"
                  :options="viewActions(item.view, viewDialogConfig)"
                >
                  <template #default="{ open }">
                    <Button
                      variant="ghost"
                      icon="lucide-more-horizontal"
                      class="me-1 !size-6 rounded !text-ink-gray-7"
                      :class="
                        open
                          ? 'opacity-100'
                          : 'opacity-0 group-hover/sidebar-item:opacity-100'
                      "
                      @click.stop
                    />
                  </template>
                </Dropdown>
              </template>
            </SidebarItem>
          </nav>
        </template>
      </ScrollArea>

      <div class="mt-auto flex flex-col gap-2">
        <slot name="footer" :is-collapsed="isCollapsed" />
        <SidebarCollapseToggle v-if="!mobile" />
      </div>
    </div>
  </Sidebar>
  <CP v-if="!mobile" v-model="showCommandPalette" />
  <ViewModal
    v-if="viewDialogConfig.show"
    v-model="viewDialogConfig"
    @update="(view, action) => handleView(view, action, viewDialogConfig)"
  />
</template>

<script setup lang="ts">
import CP from "@/components/command-palette/CP.vue";
import UserMenu from "@/components/UserMenu.vue";
import { useDevice } from "@/composables";
import { currentView, useView } from "@/composables/useView";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notification";
import { useSidebarStore } from "@/stores/sidebar";
import { useTelephonyStore } from "@/stores/telephony";
import { __ } from "@/translation";
import { getIcon, isCustomerPortal } from "@/utils";
import ViewModal from "@/components/ViewModal.vue";
import {
  Button,
  createResource,
  Dropdown,
  ScrollArea,
  Sidebar,
  SidebarCollapseToggle,
  SidebarItem,
  SidebarLabel,
} from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, reactive, ref, watch } from "vue";
import type { RouteLocationRaw } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import LucideBell from "~icons/lucide/bell";
import LucideSearch from "~icons/lucide/search";
import {
  agentPortalSidebarOptions,
  customerPortalSidebarOptions,
} from "./layoutSettings";

const props = defineProps<{
  profileSettings: any[];
  mobile?: boolean;
}>();

const route = useRoute();
const router = useRouter();
const device = useDevice();
const authStore = useAuthStore();
const notificationStore = useNotificationStore();
const sidebarStore = useSidebarStore();
const { isCallingEnabled } = storeToRefs(useTelephonyStore());
const { pinnedViews, viewActions, handleView } = useView();

const showCommandPalette = ref(false);

// Local modal state for the per-view kebab menu (edit/duplicate). The action
// logic itself is shared via useView so the sidebar and breadcrumb stay in sync.
const viewDialogConfig = reactive({
  show: false,
  view: { label: "", icon: "", name: "" },
  mode: "create",
});

const collapsed = computed({
  get: () => !sidebarStore.isExpanded,
  set: (value) => sidebarStore.toggleExpanded(!value),
});

// The mobile drawer pins the sidebar open (disable-collapse), so it is never
// visually collapsed even when the store says so.
const isCollapsed = computed(() => collapsed.value && !props.mobile);

// Expanded/folded state of the collapsible view sections, keyed by label.
const closedSections = ref(new Set<string>());
const isSectionOpen = (label: string) => !closedSections.value.has(label);

function toggleSection(label: string) {
  if (isSectionOpen(label)) closedSections.value.add(label);
  else closedSections.value.delete(label);
}

// Optimistic active item: set immediately on click so the highlight is
// instant, then kept in sync with the route (browser back/forward, external
// navigation). A view's key is its name; a nav item's key is its route name.
const activeItem = ref<string | null>(currentRouteKey());

function currentRouteKey(): string | null {
  return (route.query.view as string) || (route.name as string) || null;
}

function selectItem(key: string, to: RouteLocationRaw, onSelect?: () => void) {
  activeItem.value = key;
  onSelect?.();
  router.push(to);
}

// Counts of work waiting on the agent (open tickets / tasks assigned to them)
const navCounts = createResource({
  url: "helpdesk.api.sidebar.get_nav_counts",
  auto: !isCustomerPortal.value,
});

const navItems = computed(() => {
  const options = isCustomerPortal.value
    ? customerPortalSidebarOptions
    : agentPortalSidebarOptions;
  return options
    .filter((item) => isCallingEnabled.value || item.label !== __("Call Logs"))
    .filter((item) => !item.projectManagerOnly || authStore.isProjectManager)
    .filter((item) => !item.overviewOnly || authStore.canSeeOverview)
    .map((option: any) => ({
      label: option.label,
      icon: option.icon,
      isActive: activeItem.value === option.to,
      onClick: () => selectItem(option.to, { name: option.to }),
      badge: option.countKey ? navCounts.data?.[option.countKey] : undefined,
      section: option.section,
      key: option.label,
    }));
});

const searchItem = computed(() => ({
  label: __("Search"),
  icon: LucideSearch,
  onClick: () => (showCommandPalette.value = true),
  shortcut: true,
  key: "search",
}));

// The Notifications panel's click-outside handler ignores #notifications-btn,
// so this item's own click stays the single owner of open/close.
const notificationItem = computed(() =>
  props.mobile
    ? {
        label: __("Notifications"),
        icon: LucideBell,
        isActive: activeItem.value === "Notifications",
        onClick: () => selectItem("Notifications", { name: "Notifications" }),
        badge: notificationStore.unread,
        key: "notifications",
        id: "notifications-btn",
      }
    : {
        label: __("Notifications"),
        icon: LucideBell,
        onClick: () => notificationStore.toggle(),
        badge: notificationStore.unread,
        key: "notifications",
        id: "notifications-btn",
      }
);

const sections = computed(() => {
  if (isCustomerPortal.value) {
    return [{ label: "", items: navItems.value, collapsible: false }];
  }
  const top = props.mobile
    ? [notificationItem.value]
    : [searchItem.value, notificationItem.value];
  const result = [{ label: "", items: top, collapsible: false }];
  for (const label of ["Workspace", "Directory"]) {
    const items = navItems.value.filter((item) => item.section === label);
    if (items.length)
      result.push({ label: __(label), items, collapsible: false });
  }
  if (pinnedViews.value?.length) {
    result.push({
      label: __("Private Views"),
      items: parseViews(pinnedViews.value),
      collapsible: true,
    });
  }
  return result;
});

function parseViews(views: any[]) {
  return views.map((view) => ({
    label: view.label,
    icon: getIcon(view.icon),
    isActive: activeItem.value === view.name,
    onClick: () =>
      selectItem(
        view.name,
        { name: view.route_name, query: { view: view.name } },
        () => {
          currentView.value = { label: view.label, icon: view.icon };
        }
      ),
    key: view.name,
    view,
  }));
}

watch(
  () => [route.name, route.query.view],
  () => {
    activeItem.value = currentRouteKey();
    if (!isCustomerPortal.value) navCounts.reload();
  }
);
</script>
