<template>
  <!-- Rail (areas) and panel (the chosen area's pages). The panel only folds to
       icons and opens with its button; nothing here collapses on its own. -->
  <div
    class="flex h-full shrink-0"
    :class="mobile && 'w-[min(20rem,calc(100vw-2rem))] bg-surface-sidebar'"
  >
    <NavRail
      :areas="areas"
      :selected-area-id="selectedArea?.id"
      :active-area-id="active?.areaId"
      :profile-settings="profileSettings"
      :mobile="mobile"
      @select="selectArea"
      @notifications="openNotifications"
    />
    <!-- On desktop the panel folds to an icon column instead of leaving; the wrapper
         animates the width and clips what the narrower column cannot show. -->
    <div
      :class="
        mobile
          ? 'contents'
          : [
              'h-full shrink-0 overflow-hidden transition-[width] duration-200 motion-reduce:transition-none',
              sidebarStore.isPanelOpen ? 'w-60' : 'w-14',
            ]
      "
    >
      <NavPanel
        v-if="mobile || sidebarStore.isPanelOpen"
        :area="selectedArea"
        :active-id="active?.itemId"
        :counts="navCounts.data"
        :show-search="showSearch"
        :show-follow-ups="showFollowUps"
        :follow-ups="navCounts.data?.follow_ups"
        :view-actions="viewOptions"
        :mobile="mobile"
        @search="showCommandPalette = true"
      >
        <template #footer><slot name="footer" /></template>
        <template #footer-items><slot name="footer-items" /></template>
      </NavPanel>
      <NavPanelCollapsed
        v-else
        :area="selectedArea"
        :active-id="active?.itemId"
        :counts="navCounts.data"
        :show-search="showSearch"
        :show-follow-ups="showFollowUps"
        :follow-ups="navCounts.data?.follow_ups"
        @search="showCommandPalette = true"
      >
        <template #footer-items><slot name="collapsed-footer" /></template>
      </NavPanelCollapsed>
    </div>
  </div>
  <!-- the palette finds tickets and articles, none of which a salesperson opens -->
  <CP
    v-if="!mobile && !authStore.isSalesEmployee"
    v-model="showCommandPalette"
  />
  <ViewModal
    v-if="viewDialogConfig.show"
    v-model="viewDialogConfig"
    @update="(view, action) => handleView(view, action, viewDialogConfig)"
  />
</template>

<script setup lang="ts">
import CP from "@/components/command-palette/CP.vue";
import ViewModal from "@/components/ViewModal.vue";
import { useView } from "@/composables/useView";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notification";
import { useSidebarStore } from "@/stores/sidebar";
import { isCustomerPortal } from "@/utils";
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import NavPanel from "./NavPanel.vue";
import NavPanelCollapsed from "./NavPanelCollapsed.vue";
import NavRail from "./NavRail.vue";
import { useNavigation } from "./useNavigation";

const props = defineProps<{
  profileSettings: any[];
  mobile?: boolean;
}>();

const router = useRouter();
const authStore = useAuthStore();
const notificationStore = useNotificationStore();
const sidebarStore = useSidebarStore();
const { viewActions, handleView } = useView();
const { areas, active, selectedArea, navCounts } = useNavigation();

const showCommandPalette = ref(false);

// Local modal state for the per-view kebab menu (edit/duplicate). The action
// logic itself is shared via useView so the sidebar and breadcrumb stay in sync.
const viewDialogConfig = reactive({
  show: false,
  view: { label: "", icon: "", name: "" },
  mode: "create",
});

// one function for the panel's lifetime: an inline arrow is new on every render and would
// re-render the whole panel on each route change
const viewOptions = (view: any) => viewActions(view, viewDialogConfig);
const showSearch = computed(
  () => !props.mobile && !isCustomerPortal.value && !authStore.isSalesEmployee
);

const showFollowUps = computed(
  () => !isCustomerPortal.value && !authStore.isSalesEmployee
);

// On a desktop another area opens its first page, so a click always changes the
// screen (only swapping the panel's links went unnoticed with the panel folded to
// icons). On a phone the drawer lists the area's pages to pick from, so only an
// area with a single page opens it. The area already open only shows its pages.
// The panel stays as the person left it, open or folded to icons.
function selectArea(areaId: string) {
  sidebarStore.selectedAreaId = areaId;
  if (active.value?.areaId === areaId) return;
  const area = areas.value.find((a) => a.id === areaId);
  const pages = area?.groups.flatMap((g) => g.items) || [];
  const hasTrees = area?.groups.some((g) => g.trees?.length);
  if (!pages.length || (props.mobile && (pages.length > 1 || hasTrees))) return;
  router.push({ name: pages[0].to, query: pages[0].query });
}

// The Notifications panel's click-outside handler ignores #notifications-btn,
// so this button's own click stays the single owner of open/close.
function openNotifications() {
  if (props.mobile) router.push({ name: "Notifications" });
  else notificationStore.toggle();
}
</script>
