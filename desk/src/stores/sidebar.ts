import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { useStorage } from "@vueuse/core";
import { useAuthStore } from "@/stores/auth";

// The rail is 3.5rem and the panel 15rem open or 3.5rem folded to icons; the
// Notifications panel anchors against their sum.
const RAIL_WIDTH = 3.5;
const PANEL_WIDTH = 15;
const FOLDED_PANEL_WIDTH = 3.5;

export const useSidebarStore = defineStore("sidebar", () => {
  // Per person, so two people on one browser keep their own menu. The panel opens
  // and closes only when the person presses its button, never on its own.
  // useStorage already catches storage that is blocked or full and falls back
  // to memory.
  // The keys follow the signed-in person: the user loads after the store is made.
  const auth = useAuthStore();
  const who = computed(() => auth.userId || "guest");
  // Until the person chooses, the panel starts folded below lg: on a tablet its 15rem
  // would leave the page too narrow to use.
  const isPanelOpen = useStorage(
    computed(() => `nav_panel_open:${who.value}`),
    window.matchMedia("(min-width: 1024px)").matches
  );
  // folded-open items (a tree of saved views); only a click folds one shut
  const openTrees = useStorage<Record<string, boolean>>(
    computed(() => `nav_trees:${who.value}`),
    {}
  );
  // the rail icon whose items the panel shows
  const selectedAreaId = ref<string | null>(null);

  const width = computed(
    () =>
      `${
        RAIL_WIDTH + (isPanelOpen.value ? PANEL_WIDTH : FOLDED_PANEL_WIDTH)
      }rem`
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
