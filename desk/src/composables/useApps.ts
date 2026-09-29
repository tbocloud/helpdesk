import { createResource } from "frappe-ui";
import { computed, h, markRaw, type Component, type ComputedRef } from "vue";
import AppsIcon from "@/components/icons/AppsIcon.vue";
import { useAuthStore } from "@/stores/auth";

export interface App {
  name: string;
  logo: string;
  title: string;
  route: string;
}

const deskApp: App = {
  name: "frappe",
  logo: "/assets/helpdesk/desk/desk.png",
  title: "Desk",
  route: "/desk/helpdesk",
};

interface AppsMenuOption {
  label: string;
  icon: Component;
  submenu: Array<{ label: string; icon: unknown; onClick: () => void }>;
}

/**
 * Fetches the Frappe apps the user can switch to (Desk, ERPNext, CRM, ...) and
 * exposes them as a native Dropdown submenu option that opens on hover.
 *
 * Mirrors the apps switcher in frappe/builder (`DashboardSidebar.vue`): plain
 * `label`/`icon`/`onClick` items so reka's submenu hover-intent works cleanly.
 */
export function useApps() {
  const resource = createResource({
    url: "frappe.apps.get_apps",
    cache: "apps",
    auto: true,
    transform: (data: App[]) => {
      const apps = [deskApp];
      data.forEach((app) => {
        if (app.name === "helpdesk") return;
        apps.push({
          name: app.name,
          logo: app.logo,
          title: app.title,
          route: app.route,
        });
      });
      return apps;
    },
  });

  const authStore = useAuthStore();
  // only System Managers may use the Frappe desk; the server redirects everyone else
  const isDeskRoute = (route: string) => /^\/(app|desk)(\/|$)/.test(route || "");
  const apps = computed<App[]>(() =>
    (resource.data ?? []).filter(
      (app: App) => authStore.isAdmin || !isDeskRoute(app.route)
    )
  );

  const appsMenuOption: ComputedRef<AppsMenuOption> = computed(() => ({
    label: "Apps",
    icon: markRaw(AppsIcon),
    submenu: apps.value.map((app) => ({
      label: app.title,
      icon: h("img", { src: app.logo }),
      onClick: () => window.open(app.route, "_self"),
    })),
  }));

  return { apps, appsMenuOption };
}
