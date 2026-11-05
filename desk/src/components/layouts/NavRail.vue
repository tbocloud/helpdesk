<template>
  <nav
    :aria-label="__('Areas')"
    class="flex h-full w-14 shrink-0 flex-col items-center gap-1 bg-[color:var(--surface-rail)] py-3"
  >
    <RailButton
      v-if="!mobile"
      :label="sidebarStore.isPanelOpen ? __('Hide menu') : __('Show menu')"
      aria-controls="nav-panel"
      :aria-expanded="sidebarStore.isPanelOpen"
      @click="sidebarStore.isPanelOpen = !sidebarStore.isPanelOpen"
    >
      <LucidePanelLeftClose
        v-if="sidebarStore.isPanelOpen"
        class="size-4"
        aria-hidden="true"
      />
      <LucidePanelLeftOpen v-else class="size-4" aria-hidden="true" />
    </RailButton>
    <BrandLogo v-else class="!size-9 !rounded-[8px]" />

    <div
      class="my-2 h-px w-6 bg-[color:var(--rail-hover)]"
      aria-hidden="true"
    />

    <ul class="flex flex-col items-center gap-1">
      <li v-for="area in areas" :key="area.id">
        <RailButton
          :label="area.label"
          :active="area.id === selectedAreaId"
          :current="area.id === activeAreaId"
          :mobile="mobile"
          :aria-current="area.id === activeAreaId ? 'true' : undefined"
          @click="emit('select', area.id)"
        >
          <component :is="area.icon" class="size-5" aria-hidden="true" />
        </RailButton>
      </li>
    </ul>

    <div class="mt-auto flex flex-col items-center gap-1">
      <FollowUpStrip
        v-if="showFollowUps && !mobile && !sidebarStore.isPanelOpen"
        :summary="followUps"
        compact
        rail
      />
      <RailButton
        v-if="!isCustomerPortal"
        id="notifications-btn"
        :label="notificationLabel"
        :mobile="mobile"
        :dot="notificationStore.unread > 0"
        @click="emit('notifications')"
      >
        <LucideBell class="size-5" aria-hidden="true" />
      </RailButton>
      <RailButton
        v-if="!mobile && !isCustomerPortal"
        :label="__('Settings')"
        @click="showSettingsModal = true"
      >
        <LucideSettings class="size-5" aria-hidden="true" />
      </RailButton>
      <Dropdown :options="profileSettings" side="right" align="end">
        <template #default="{ open }">
          <button
            type="button"
            class="mt-1 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :class="open && 'ring-2 ring-[color:var(--ink-rail)]'"
            :aria-label="__('{0} menu', String(authStore.userName || ''))"
          >
            <Avatar
              :image="authStore.userImage"
              :label="authStore.userName"
              size="lg"
            />
          </button>
        </template>
      </Dropdown>
    </div>
  </nav>
</template>

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo.vue";
import FollowUpStrip from "@/components/FollowUpStrip.vue";
import { showSettingsModal } from "@/components/Settings/settingsModal";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notification";
import { useSidebarStore } from "@/stores/sidebar";
import { __ } from "@/translation";
import { isCustomerPortal } from "@/utils";
import { Avatar, Dropdown } from "frappe-ui";
import { computed } from "vue";
import LucideBell from "~icons/lucide/bell";
import LucidePanelLeftClose from "~icons/lucide/panel-left-close";
import LucidePanelLeftOpen from "~icons/lucide/panel-left-open";
import LucideSettings from "~icons/lucide/settings";
import RailButton from "./RailButton.vue";
import type { NavArea } from "./navigation";

const props = defineProps<{
  areas: NavArea[];
  selectedAreaId?: string | null;
  /** the area holding the page being viewed */
  activeAreaId?: string | null;
  profileSettings: any[];
  followUps?: any;
  showFollowUps?: boolean;
  mobile?: boolean;
}>();

const emit = defineEmits<{
  (e: "select", areaId: string): void;
  (e: "notifications"): void;
}>();

const authStore = useAuthStore();
const notificationStore = useNotificationStore();
const sidebarStore = useSidebarStore();

const notificationLabel = computed(() =>
  notificationStore.unread
    ? __("Notifications ({0} unread)", String(notificationStore.unread))
    : __("Notifications")
);
</script>
