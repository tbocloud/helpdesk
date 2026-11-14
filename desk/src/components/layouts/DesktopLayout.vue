<template>
  <div class="flex h-screen w-full overflow-hidden bg-surface-sidebar">
    <Sidebar />
    <!-- The page sits on a raised panel inset from the shell; it scrolls on its own.
         tabindex="-1": Escape in the auto-hide sidebar hands keyboard focus here. -->
    <main
      tabindex="-1"
      class="relative my-2.5 me-2.5 flex min-w-0 flex-1 flex-col overflow-auto rounded-2xl border border-outline-gray-2 bg-surface-base shadow-sm"
    >
      <AppHeader />
      <slot />
    </main>
    <Notifications />
    <PendingCalls v-if="authStore.canUseLeads" />
    <CallBox v-if="authStore.canUseLeads" />
  </div>
</template>
<script setup>
import { Notifications } from "@/components";
import CallBox from "@/pages/leads/CallBox.vue";
import PendingCalls from "@/pages/leads/PendingCalls.vue";
import { useAuthStore } from "@/stores/auth";
import AppHeader from "./AppHeader.vue";
import Sidebar from "./Sidebar.vue";

const authStore = useAuthStore();
</script>
