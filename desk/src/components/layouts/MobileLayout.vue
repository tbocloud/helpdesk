<template>
  <div class="flex h-screen w-screen">
    <MobileSidebar />
    <div class="flex h-full flex-col flex-1 overflow-auto">
      <MobileAppHeader />
      <slot />
    </div>
    <PendingCalls v-if="authStore.canUseLeads" />
    <CallBox v-if="authStore.canUseLeads" />
  </div>
</template>
<script setup>
import CallBox from "@/pages/leads/CallBox.vue";
import PendingCalls from "@/pages/leads/PendingCalls.vue";
import { useAuthStore } from "@/stores/auth";
import MobileSidebar from "./MobileSidebar.vue";
import MobileAppHeader from "./MobileAppHeader.vue";

const authStore = useAuthStore();
</script>
