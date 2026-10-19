<template>
  <Telephony v-if="step === 'telephony-settings'" @updateStep="updateStep" />
  <TwilioSettings
    v-else-if="step === 'twilio-settings'"
    @updateStep="updateStep"
  />
  <ExotelSettings
    v-else-if="step === 'exotel-settings'"
    @updateStep="updateStep"
  />
  <MyOperatorSettings
    v-else-if="step === 'myoperator-settings'"
    @update-step="updateStep"
  />
</template>
<script setup>
import Telephony from "./Telephony.vue";
import ExotelSettings from "./ExotelSettings.vue";
import TwilioSettings from "./TwilioSettings.vue";
import MyOperatorSettings from "./MyOperatorSettings.vue";
import { useAuthStore } from "@/stores/auth";
import { ref } from "vue";

// Twilio and Exotel need the telephony app; without it MyOperator (lead calls on the
// ERP site) is all there is to set up
const step = ref(
  useAuthStore().telephonyInstalled
    ? "telephony-settings"
    : "myoperator-settings"
);

function updateStep(newStep) {
  step.value = newStep;
}
</script>
