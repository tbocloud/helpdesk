import { currentView, useView } from "@/composables/useView";
import {
  CONTENT_ROUTES,
  CONTENT_TEAM_ROUTES,
  DM_EMPLOYEE_HIDDEN_ROUTES,
  ERP_EMPLOYEE_HIDDEN_ROUTES,
  SALES_EMPLOYEE_ROUTES,
} from "@/pages/content/contentTeam";
import { useAuthStore } from "@/stores/auth";
import { useSidebarStore } from "@/stores/sidebar";
import { __ } from "@/translation";
import { getIcon, isCustomerPortal } from "@/utils";
import { createResource } from "frappe-ui";
import { computed, watch } from "vue";
import { useRoute } from "vue-router";
import LucideBookmark from "~icons/lucide/bookmark";
import {
  agentNavAreas,
  customerNavAreas,
  type NavArea,
  type NavChild,
  type NavItem,
} from "./navigation";

/**
 * What the sidebar shows this person, and where they are in it. The role and
 * department rules live here, once: a page someone can't use never appears.
 */
export function useNavigation() {
  const route = useRoute();
  const authStore = useAuthStore();
  const sidebarStore = useSidebarStore();
  const { pinnedViews } = useView();

  // Counts of work waiting on the agent (open tickets / tasks assigned to them)
  const navCounts = createResource({
    url: "helpdesk.api.sidebar.get_nav_counts",
    auto: !isCustomerPortal.value,
  });

  function isItemVisible(item: NavItem) {
    const to = item.to;
    if (isCustomerPortal.value) return true;
    return (
      (!item.ticketWorkersOnly || authStore.canWorkTickets) &&
      (authStore.inContentTeam || !CONTENT_ROUTES.has(to)) &&
      (!authStore.isErpOnly || !ERP_EMPLOYEE_HIDDEN_ROUTES.has(to)) &&
      (!authStore.isDmEmployee || !DM_EMPLOYEE_HIDDEN_ROUTES.has(to)) &&
      (!authStore.isSalesEmployee || SALES_EMPLOYEE_ROUTES.has(to)) &&
      (!item.leadsOnly || authStore.canUseLeads) &&
      (!item.leadBankOnly || authStore.canUseLeadBank) &&
      (!item.projectManagerOnly || authStore.isProjectManager) &&
      (!item.overviewOnly || authStore.canSeeOverview) &&
      (!item.adoptionOnly || authStore.canSeeAdoption) &&
      (!item.customerReportOnly || authStore.canSeeCustomerReport) &&
      (!authStore.isContentTeam || CONTENT_TEAM_ROUTES.has(to))
    );
  }

  // saved views are ticket views, which a salesperson doesn't open
  const savedViews = computed<NavChild[]>(() =>
    authStore.isSalesEmployee || isCustomerPortal.value
      ? []
      : (pinnedViews.value || []).map((view: any) => ({
          id: view.name,
          label: view.label,
          icon: getIcon(view.icon),
          to: { name: view.route_name, query: { view: view.name } },
          view,
          onSelect: () => {
            currentView.value = { label: view.label, icon: view.icon };
          },
        }))
  );

  const areas = computed<NavArea[]>(() => {
    const source = isCustomerPortal.value ? customerNavAreas : agentNavAreas;
    return source
      .map((area) => ({
        ...area,
        groups: area.groups
          .map((group, index) => ({
            ...group,
            items: group.items.filter(isItemVisible),
            trees:
              area.id === "support" && index === 0 && savedViews.value.length
                ? [
                    {
                      id: "saved-views",
                      label: __("Saved views"),
                      icon: LucideBookmark,
                      children: savedViews.value,
                    },
                  ]
                : [],
          }))
          .filter((group) => group.items.length || group.trees.length),
      }))
      .filter((area) => area.groups.length);
  });

  // The page the route belongs to: a saved view wins over its list page, and a
  // detail page (a ticket, a project tab) keeps its list page highlighted.
  const active = computed<{
    areaId: string;
    itemId: string;
    treeId?: string;
  } | null>(() => {
    const view = route.query.view as string | undefined;
    const name = route.name as string;
    for (const area of areas.value) {
      for (const group of area.groups) {
        for (const tree of group.trees || []) {
          if (view && tree.children.some((child) => child.id === view)) {
            return { areaId: area.id, itemId: view, treeId: tree.id };
          }
        }
      }
    }
    for (const area of areas.value) {
      for (const group of area.groups) {
        const item = group.items.find(
          (i) => i.to === name || i.also?.includes(name)
        );
        if (item) return { areaId: area.id, itemId: item.id };
      }
    }
    return null;
  });

  // A deep link or any navigation shows the area the page belongs to, and opens
  // (never closes) the tree holding it. Picking another area by hand sticks
  // until the next navigation.
  watch(
    () => `${route.fullPath}|${active.value?.areaId}`,
    () => {
      if (!active.value) return;
      sidebarStore.selectedAreaId = active.value.areaId;
      if (active.value.treeId) {
        sidebarStore.setTreeOpen(active.value.treeId, true);
      }
    },
    { immediate: true }
  );

  watch(
    () => [route.name, route.query.view],
    () => {
      if (!isCustomerPortal.value) navCounts.reload();
    }
  );

  const selectedArea = computed(
    () =>
      areas.value.find((area) => area.id === sidebarStore.selectedAreaId) ||
      areas.value[0]
  );

  return { areas, active, selectedArea, navCounts };
}
