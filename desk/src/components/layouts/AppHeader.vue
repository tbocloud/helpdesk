<template>
  <div class="flex items-start gap-4 px-8 pt-5">
    <div id="app-header" class="w-full min-w-0 flex-1"></div>
    <div class="flex items-start justify-center empty:hidden">
      <CallUI :userEmail="user" />
    </div>
  </div>
</template>

<script setup>
import CallUI from "@/components/telephony/CallUI.vue";
import { useAuthStore } from "@/stores/auth";
import { useTelephonyStore } from "@/stores/telephony";
import { onMounted } from "vue";

const { user } = useAuthStore();

const telephonyStore = useTelephonyStore();

onMounted(() => {
  telephonyStore.fetchCallIntegrationStatus();
});
</script>
