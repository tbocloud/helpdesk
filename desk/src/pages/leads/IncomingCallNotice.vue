<template>
  <!-- a call coming in to the person's phone -->
  <section
    v-if="incoming && !box.open"
    role="alert"
    :aria-labelledby="titleId"
    class="fixed inset-x-0 bottom-0 z-40 flex flex-col gap-4 rounded-t-2xl border border-outline-gray-2 bg-surface-base p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-lg sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-96 sm:rounded-xl sm:pb-4"
  >
    <header class="flex items-center gap-2 text-ink-gray-9">
      <LucidePhoneIncoming class="size-5 shrink-0" aria-hidden="true" />
      <h2 :id="titleId" class="text-lg-medium">{{ __("Incoming call") }}</h2>
    </header>
    <div class="flex items-center gap-3">
      <CallAvatar :name="incoming.lead_name" />
      <div class="min-w-0 flex-1">
        <p class="truncate text-lg-medium text-ink-gray-9">
          {{ incoming.lead_name || __("A number we don't know yet") }}
        </p>
        <p
          v-if="incoming.number"
          class="font-mono text-base tabular-nums text-ink-gray-7"
        >
          {{ incoming.number }}
        </p>
      </div>
    </div>
    <p class="flex items-center gap-2 text-sm text-ink-gray-8">
      <LucidePhone class="size-4 shrink-0" aria-hidden="true" />
      {{ __("It is ringing on your phone. Pick up there.") }}
    </p>
    <div class="flex gap-2">
      <Button
        class="!h-11 flex-1"
        :label="__('Dismiss')"
        @click="dismissIncoming()"
      />
      <Button
        v-if="incoming.lead"
        class="!h-11 flex-1"
        variant="solid"
        :label="__('Open lead')"
        :link="`/helpdesk/leads/${encodeURIComponent(incoming.lead)}`"
        @click="dismissIncoming()"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { startRing, stopRing } from "@/composables/ringTone";
import { __ } from "@/translation";
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { Button } from "frappe-ui";
import { onMounted, useId, watch } from "vue";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneIncoming from "~icons/lucide/phone-incoming";
import CallAvatar from "./CallAvatar.vue";
import { box } from "./callBox";
import {
  checkIncoming,
  dismissIncoming,
  incoming,
  INCOMING_POLL_MS,
} from "./incomingCall";

const titleId = useId();

// asked every 10 seconds while the tab is visible, with a ring that plays only where the
// browser lets it
const visible = useDocumentVisibility();
const { pause, resume } = useIntervalFn(checkIncoming, INCOMING_POLL_MS, {
  immediate: false,
});
onMounted(() => {
  if (visible.value === "visible") {
    checkIncoming();
    resume();
  }
});
watch(visible, (state) => {
  if (state === "visible") {
    checkIncoming();
    resume();
  } else pause();
});
watch(
  () => incoming.value?.call,
  (ringing) => {
    if (ringing && !box.open) startRing("incoming");
    else stopRing("incoming");
  }
);
</script>
