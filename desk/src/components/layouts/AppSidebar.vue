<template>
  <Sidebar v-model:collapsed="collapsed" :disable-collapse="mobile">
    <div class="flex h-full flex-col" :class="isCollapsed ? 'p-2' : 'p-3'">
      <UserMenu :options="profileSettings" :is-collapsed="isCollapsed" />

      <button
        v-if="showSearchCard"
        type="button"
        class="mt-3 flex h-10 w-full shrink-0 items-center gap-2.5 rounded-[12px] border border-outline-gray-2 bg-surface-base px-2 text-start transition-colors hover:bg-surface-gray-1"
        @click="showCommandPalette = true"
      >
        <span
          class="grid size-6 shrink-0 place-items-center rounded-[6px] bg-surface-gray-2 text-ink-gray-6"
        >
          <LucideSearch class="size-3.5" aria-hidden="true" />
        </span>
        <span class="flex-1 truncate text-base text-ink-gray-6">
          {{ __("Search") }}
        </span>
        <kbd
          class="flex items-center gap-0.5 rounded-[4px] bg-surface-gray-2 px-1.5 py-0.5 text-2xs text-ink-gray-6"
        >
          <component
            :is="device.modifierIcon"
            class="size-3"
            aria-hidden="true"
          />
          K
        </kbd>
      </button>

      <ScrollArea class="mt-2 min-h-0 flex-1 -mx-2" viewport-class="px-2">
        <template v-for="(section, index) in sections" :key="index">
          <template v-if="section.label && !section.collapsible">
            <div
              v-if="!isCollapsed"
              class="mb-1 mt-4 select-none px-3 text-2xs font-semibold uppercase tracking-[0.08em] text-ink-gray-5"
            >
              {{ section.label }}
            </div>
            <div v-else class="mx-1 my-2 border-t border-outline-gray-2" />
          </template>
          <SidebarLabel
            v-else-if="section.label"
            divider
            class="mt-3 mb-1 select-none"
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
                <span class="tbo-nav-icon relative">
                  <component
                    :is="item.icon"
                    class="size-3.5"
                    aria-hidden="true"
                  />
                  <span
                    v-if="
                      item.key === 'notifications' && item.badge && isCollapsed
                    "
                    class="absolute -end-1 -top-1 size-2 rounded-full bg-brand ring-2 ring-[color:var(--surface-sidebar)]"
                  />
                </span>
              </template>
              <span class="tbo-nav-label ms-1 truncate text-base">
                {{ __(item.label) }}
              </span>
              <template #suffix>
                <kbd
                  v-if="item.shortcut"
                  class="me-2 flex items-center gap-0.5 rounded-[4px] bg-surface-gray-2 px-1.5 py-0.5 text-2xs text-ink-gray-6"
                >
                  <component :is="device.modifierIcon" class="size-3" />
                  K
                </kbd>
                <template
                  v-else-if="item.key === 'notifications' && !isCollapsed"
                >
                  <span
                    v-if="item.badge"
                    class="me-1 font-mono text-xs tabular-nums text-ink-gray-5"
                    :aria-label="__('{0} unread', String(item.badge))"
                  >
                    {{ item.badge > 99 ? "99+" : item.badge }}
                  </span>
                  <Button
                    variant="ghost"
                    class="me-0.5 !text-ink-gray-6"
                    :tooltip="themeToggle.label.value"
                    :label="themeToggle.label.value"
                    @click="themeToggle.toggle()"
                  >
                    <template #icon>
                      <component
                        :is="themeToggle.icon.value"
                        class="size-3.5"
                        aria-hidden="true"
                      />
                    </template>
                  </Button>
                </template>
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
                      :aria-label="__('View options')"
                      @click.stop
                    />
                  </template>
                </Dropdown>
              </template>
            </SidebarItem>
          </nav>
        </template>
      </ScrollArea>

      <div class="mt-auto flex flex-col gap-2 pt-2">
        <slot name="footer" :is-collapsed="isCollapsed" />
        <div
          v-if="!mobile || $slots['footer-items']"
          class="flex flex-col gap-0.5 border-t border-outline-gray-2 pt-2"
        >
          <slot name="footer-items" :is-collapsed="isCollapsed" />
          <SidebarItem
            v-if="!mobile"
            :label="isCollapsed ? __('Expand') : __('Collapse')"
            @click="collapsed = !collapsed"
          >
            <template #prefix>
              <span class="tbo-nav-icon">
                <LucidePanelLeftOpen
                  v-if="isCollapsed"
                  class="size-3.5"
                  aria-hidden="true"
                />
                <LucidePanelLeftClose
                  v-else
                  class="size-3.5"
                  aria-hidden="true"
                />
              </span>
            </template>
            <span class="ms-1 truncate text-base text-ink-gray-5">
              {{ isCollapsed ? __("Expand") : __("Collapse") }}
            </span>
          </SidebarItem>
        </div>
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
import {
  CONTENT_ROUTES,
  ERP_EMPLOYEE_HIDDEN_ROUTES,
  CONTENT_TEAM_ROUTES,
  DEPARTMENT_EMPLOYEE_HIDDEN_ROUTES,
} from "@/pages/content/contentTeam";
import CP from "@/components/command-palette/CP.vue";
import UserMenu from "@/components/UserMenu.vue";
import { useDevice } from "@/composables";
import { useThemeToggle } from "@/composables/useThemeToggle";
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
  SidebarItem,
  SidebarLabel,
} from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, reactive, ref, watch } from "vue";
import type { RouteLocationRaw } from "vue-router";
import { useRoute, useRouter } from "vue-router";
import LucideBell from "~icons/lucide/bell";
import LucidePanelLeftClose from "~icons/lucide/panel-left-close";
import LucidePanelLeftOpen from "~icons/lucide/panel-left-open";
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
const themeToggle = useThemeToggle();

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
    .filter((item) => !item.adminOnly || authStore.isAdmin)
    .filter((item) => authStore.inContentTeam || !CONTENT_ROUTES.has(item.to))
    .filter(
      (item) => !authStore.isErpOnly || !ERP_EMPLOYEE_HIDDEN_ROUTES.has(item.to)
    )
    .filter(
      (item) =>
        !authStore.isDepartmentEmployee ||
        !DEPARTMENT_EMPLOYEE_HIDDEN_ROUTES.has(item.to)
    )
    .filter((item) => !item.projectManagerOnly || authStore.isProjectManager)
    .filter((item) => !item.overviewOnly || authStore.canSeeOverview)
    .filter(
      (item) => !item.customerReportOnly || authStore.canSeeCustomerReport
    )
    .filter(
      (item) =>
        !authStore.isContentTeam ||
        isCustomerPortal.value ||
        CONTENT_TEAM_ROUTES.has(item.to)
    )
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

const showSearchCard = computed(
  () => !props.mobile && !isCustomerPortal.value && !isCollapsed.value
);

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

const themeRailItem = computed(() => ({
  label: themeToggle.label.value,
  icon: themeToggle.icon.value,
  onClick: themeToggle.toggle,
  key: "theme",
}));

const sections = computed(() => {
  if (isCustomerPortal.value) {
    return [{ label: "", items: navItems.value, collapsible: false }];
  }
  // Expanded desktop shows search as its own card above the nav; collapsed it
  // falls back to a rail item so it keeps its tooltip.
  const top =
    props.mobile || showSearchCard.value
      ? [notificationItem.value]
      : [searchItem.value, notificationItem.value];
  // Expanded, the theme button sits in the Notifications row; the collapsed
  // rail hides row suffixes, so it gets its own rail item there.
  if (isCollapsed.value) top.push(themeRailItem.value);
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
