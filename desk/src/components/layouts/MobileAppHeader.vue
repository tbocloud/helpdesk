<template>
  <div
    class="flex min-h-12 items-center border-b border-outline-gray-2 bg-surface-base"
  >
    <div class="z-20 -mr-4 ml-1 flex items-center justify-center">
      <Button variant="ghosted" @click="sidebarOpened = !sidebarOpened">
        <FeatherIcon name="menu" class="size-4" />
      </Button>
    </div>
    <HeaderBack class="z-20 ml-4 shrink-0" />
    <header id="app-header" class="w-full"></header>
  </div>
  <CallUI class="mr-3 mt-2" :userEmail="user" />
</template>

<script setup>
import { mobileSidebarOpened as sidebarOpened } from "@/composables/mobile";
import CallUI from "../telephony/CallUI.vue";
import { useAuthStore } from "@/stores/auth";
import { useTelephonyStore } from "@/stores/telephony";
import { onMounted } from "vue";
import HeaderBack from "./HeaderBack.vue";

const { user } = useAuthStore();

const telephonyStore = useTelephonyStore();

onMounted(() => {
  telephonyStore.fetchCallIntegrationStatus();
});
</script>
