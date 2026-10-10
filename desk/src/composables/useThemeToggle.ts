import { __ } from "@/translation";
import { usePreferredDark } from "@vueuse/core";
import { useTheme } from "frappe-ui";
import { computed } from "vue";
import LucideMoon from "~icons/lucide/moon";
import LucideSun from "~icons/lucide/sun";

/**
 * One-click light/dark switch shared by the sidebar button and the profile
 * menus. frappe-ui's toggleTheme() treats "system" as light, so a user on
 * "system" with a dark OS would need two clicks; this flips what is shown.
 */
export function useThemeToggle() {
  const { currentTheme, setTheme } = useTheme();
  const prefersDark = usePreferredDark();

  const isDark = computed(() =>
    currentTheme.value === "system"
      ? prefersDark.value
      : currentTheme.value === "dark"
  );
  const label = computed(() =>
    isDark.value ? __("Switch to light theme") : __("Switch to dark theme")
  );
  const icon = computed(() => (isDark.value ? LucideSun : LucideMoon));

  function toggle() {
    setTheme(isDark.value ? "light" : "dark");
  }

  const menuItem = computed(() => ({
    label: label.value,
    icon: icon.value,
    onClick: toggle,
  }));

  return { label, icon, toggle, menuItem };
}
