import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { useStorage } from "@vueuse/core";
import { useAuthStore } from "@/stores/auth";

// The rail is 3.5rem and the panel 15rem; the Notifications panel anchors
// against their sum.
const RAIL_WIDTH = 3.5;
const PANEL_WIDTH = 15;

export const useSidebarStore = defineStore("sidebar", () => {
  // Per person, so two people on one browser keep their own menu. The panel opens
  // and closes only when the person presses its button, never on its own.
  // useStorage already catches storage that is blocked or full and falls back
  // to memory.
  const who = useAuthStore().userId || "guest";
  const isPanelOpen = useStorage(`nav_panel_open:${who}`, true);
  // folded-open items (a tree of saved views); only a click folds one shut
  const openTrees = useStorage<Record<string, boolean>>(`nav_trees:${who}`, {});
  // the rail icon whose items the panel shows
  const selectedAreaId = ref<string | null>(null);

  const width = computed(
    () => `${RAIL_WIDTH + (isPanelOpen.value ? PANEL_WIDTH : 0)}rem`
  );

  // trees open until their person closes them
  const isTreeOpen = (id: string) => openTrees.value[id] !== false;
  function setTreeOpen(id: string, open: boolean) {
    openTrees.value = { ...openTrees.value, [id]: open };
  }

  return {
    isPanelOpen,
    selectedAreaId,
    width,
    isTreeOpen,
    setTreeOpen,
  };
});
