import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { useStorage } from "@vueuse/core";

export const useSidebarStore = defineStore("sidebar", () => {
  // Desktop: pinned keeps the sidebar open beside the page; otherwise it rests
  // as the icon rail and expands over the page while pointed at or focused.
  // A new key, so everyone starts on auto-hide rather than inheriting the old
  // "sidebar_is_expanded" (true for nearly everyone). useStorage already
  // catches storage that is blocked or full and falls back to memory.
  const isPinned = useStorage("sidebar_is_pinned", false);
  const isPeeking = ref(false);
  const isExpanded = computed(() => isPinned.value || isPeeking.value);
  // Match frappe-ui Sidebar's width/collapsedWidth props (15rem/3rem),
  // since the notifications panel anchors against this value.
  const width = computed(() => {
    return isExpanded.value ? "15rem" : "3rem";
  });

  return {
    isExpanded,
    isPeeking,
    isPinned,
    width,
  };
});
