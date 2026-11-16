<template>
  <div class="flex h-screen w-full overflow-hidden bg-surface-sidebar">
    <Sidebar />
    <!-- The page sits on the gray canvas, its content in white cards; it scrolls on its own.
         tabindex="-1": Escape in the auto-hide sidebar hands keyboard focus here. -->
    <main
      tabindex="-1"
      class="relative flex min-w-0 flex-1 flex-col overflow-auto bg-canvas"
    >
      <AppHeader />
      <slot />
    </main>
    <Notifications />
    <!-- the staff assistant's panel (Phase 6): the same chat as the TBO Copilot bot in Teams -->
    <CopilotChatPanel v-if="!isCustomerPortal" />
    <PendingCalls v-if="authStore.canUseLeads" />
    <CallBox v-if="authStore.canUseLeads" />
  </div>
</template>
<script setup>
import { Notifications } from "@/components";
import CopilotChatPanel from "@/components/copilot/CopilotChatPanel.vue";
import CallBox from "@/pages/leads/CallBox.vue";
import PendingCalls from "@/pages/leads/PendingCalls.vue";
import { useAuthStore } from "@/stores/auth";
import { isCustomerPortal } from "@/utils";
import AppHeader from "./AppHeader.vue";
import Sidebar from "./Sidebar.vue";

const authStore = useAuthStore();
</script>
