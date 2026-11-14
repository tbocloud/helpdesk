<template>
  <!-- a call coming in to the person's phone -->
  <div
    v-if="incoming && !box.open"
    role="alert"
    class="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 shadow-lg sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-96"
  >
    <div class="flex items-start gap-3">
      <LucidePhoneIncoming
        class="mt-0.5 size-5 shrink-0 text-ink-gray-8"
        aria-hidden="true"
      />
      <div class="min-w-0 flex-1">
        <p class="text-base-medium text-ink-gray-9">
          {{ __("Incoming call") }}
        </p>
        <p class="truncate text-p-base text-ink-gray-8">
          {{ incoming.lead_name || __("A number we don't know yet") }}
        </p>
        <p
          v-if="incoming.number"
          class="font-mono text-sm tabular-nums text-ink-gray-7"
        >
          {{ incoming.number }}
        </p>
        <p class="mt-1 text-p-sm text-ink-gray-6">
          {{ __("It is ringing on your phone. Pick up there.") }}
        </p>
      </div>
    </div>
    <div class="flex justify-end gap-2">
      <Button :label="__('Dismiss')" @click="dismissIncoming()" />
      <Button
        v-if="incoming.lead"
        variant="solid"
        :label="__('Open lead')"
        :link="`/helpdesk/leads/${encodeURIComponent(incoming.lead)}`"
        @click="dismissIncoming()"
      />
    </div>
  </div>

  <!-- minimised: one small pill that says where the call is -->
  <button
    v-if="box.open && box.minimised"
    ref="pill"
    type="button"
    class="fixed bottom-[max(0.75rem,env(safe-area-inset-bottom))] right-3 z-40 flex min-h-12 max-w-[calc(100vw-1.5rem)] items-center gap-2 rounded-full border border-outline-gray-2 bg-surface-base px-4 py-2 text-sm text-ink-gray-9 shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight sm:bottom-4 sm:right-4"
    :aria-label="__('Open the call box: {0}', status.title)"
    @click="expand"
  >
    <component
      :is="status.icon"
      class="size-4 shrink-0"
      :class="status.tone"
      aria-hidden="true"
    />
    <span class="truncate">{{ box.call?.lead_name }}</span>
    <span class="shrink-0 font-mono tabular-nums text-ink-gray-7">{{
      pillText
    }}</span>
  </button>

  <section
    v-else-if="box.open"
    ref="panel"
    role="dialog"
    aria-modal="false"
    tabindex="-1"
    :aria-labelledby="titleId"
    class="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 flex max-h-[85vh] flex-col gap-4 overflow-y-auto rounded-xl border border-outline-gray-2 bg-surface-base p-4 shadow-lg focus-visible:outline-none sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-96"
    @keydown.esc.stop="onEscape"
  >
    <header class="flex items-start gap-3">
      <component
        :is="status.icon"
        class="mt-1 size-6 shrink-0"
        :class="status.tone"
        aria-hidden="true"
      />
      <div class="min-w-0 flex-1">
        <!-- read out when the call moves on -->
        <h2
          :id="titleId"
          class="text-xl-medium tabular-nums text-ink-gray-9"
          role="status"
          aria-live="polite"
        >
          {{ status.title }}
        </h2>
        <p v-if="status.hint" class="mt-0.5 text-p-sm text-ink-gray-7">
          {{ status.hint }}
        </p>
      </div>
      <div class="-mr-1 -mt-1 flex shrink-0 items-center">
        <Button
          variant="ghost"
          :aria-label="
            ringMuted ? __('Turn the ring sound on') : __('Mute the ring sound')
          "
          :aria-pressed="ringMuted"
          @click="ringMuted = !ringMuted"
        >
          <template #icon>
            <LucideVolumeX v-if="ringMuted" class="size-4" aria-hidden="true" />
            <LucideVolume2 v-else class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="canClose"
          variant="ghost"
          :aria-label="__('Close')"
          @click="closeBox()"
        >
          <template #icon>
            <LucideX class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-else
          variant="ghost"
          :aria-label="__('Minimise the call box')"
          @click="collapse"
        >
          <template #icon>
            <LucideMinus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </header>

    <div v-if="box.call" class="flex flex-col gap-0.5">
      <p class="text-lg-medium text-ink-gray-9">{{ box.call.lead_name }}</p>
      <p v-if="box.call.company" class="text-p-sm text-ink-gray-7">
        {{ box.call.company }}
      </p>
      <p
        v-if="box.number"
        class="font-mono text-sm tabular-nums text-ink-gray-7"
      >
        {{ __("Number: {0}", box.number) }}
      </p>
      <p v-if="box.call.product" class="mt-1 text-p-sm text-ink-gray-8">
        {{ __("Calling for: {0}", box.call.product) }}
        <template v-if="box.call.intro"> — {{ box.call.intro }}</template>
      </p>
      <router-link
        class="mt-1 inline-flex min-h-8 items-center gap-1 self-start rounded text-p-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :to="{ name: 'Lead', params: { leadId: box.call.lead } }"
      >
        <LucideExternalLink class="size-3.5" aria-hidden="true" />
        {{ __("Open the lead") }}
      </router-link>
    </div>

    <FormControl
      v-if="box.phase !== 'refused'"
      v-model="box.note"
      type="textarea"
      :label="__('Note for this call')"
      :rows="3"
      maxlength="500"
    />
    <p v-if="box.phase !== 'refused'" class="-mt-3 text-p-sm text-ink-gray-6">
      {{ __("It goes into how the call went, when you record the result.") }}
    </p>

    <div class="flex flex-wrap justify-end gap-2">
      <Button
        v-if="box.phase === 'refused'"
        variant="solid"
        :label="__('Try again')"
        @click="box.call && placeCall(box.call)"
      />
      <Button
        v-else-if="over || tooLong"
        :variant="over ? 'solid' : 'outline'"
        :label="__('Record the result')"
        @click="recordResult()"
      />
    </div>
    <p v-if="resultPending && over" class="text-p-sm text-ink-gray-6">
      {{ __("This box closes once you have recorded how the call went.") }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { ringMuted, startRing, stopRing } from "@/composables/ringTone";
import { __ } from "@/translation";
import { useDocumentVisibility, useIntervalFn, useNow } from "@vueuse/core";
import { Button, FormControl } from "frappe-ui";
import { computed, nextTick, onMounted, ref, useId, watch } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideMinus from "~icons/lucide/minus";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneCall from "~icons/lucide/phone-call";
import LucidePhoneIncoming from "~icons/lucide/phone-incoming";
import LucidePhoneMissed from "~icons/lucide/phone-missed";
import LucidePhoneOff from "~icons/lucide/phone-off";
import LucideVolume2 from "~icons/lucide/volume-2";
import LucideVolumeX from "~icons/lucide/volume-x";
import LucideX from "~icons/lucide/x";
import {
  box,
  canClose,
  closeBox,
  isWaiting,
  minimise,
  placeCall,
  RECORD_AFTER_MS,
  recordResult,
  resultPending,
} from "./callBox";
import {
  checkIncoming,
  dismissIncoming,
  incoming,
  INCOMING_POLL_MS,
} from "./incomingCall";
import { callLength } from "./leads";

const titleId = useId();
const panel = ref<HTMLElement | null>(null);
const pill = ref<HTMLElement | null>(null);

// the clock runs only while the box is open
const now = useNow({ interval: 1000, controls: false });

const over = computed(() => box.phase === "ended" || box.phase === "timeout");
/** without live updates the box can't tell the call is over: offer the result anyway */
const tooLong = computed(
  () =>
    isWaiting(box.phase) &&
    box.phase !== "placing" &&
    +now.value - box.startedAt > RECORD_AFTER_MS
);

/** 130 → "2m 10s" */
function spoken(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  return minutes
    ? __("{0}m {1}s", String(minutes), String(total % 60))
    : __("{0}s", String(total));
}

const status = computed(() => {
  const name = box.call?.lead_name || "";
  switch (box.phase) {
    case "placing":
    case "calling":
      return {
        icon: LucidePhoneCall,
        tone: "text-ink-gray-7",
        title: __("Calling your phone…"),
        hint: __(
          "Your phone rings first, then {0}. The call is on your phone, not on this screen.",
          name
        ),
      };
    case "ringing":
      return {
        icon: LucidePhoneIncoming,
        tone: "text-ink-gray-8",
        title: __("Pick up your phone"),
        hint: __("Your phone is ringing. The call is on your phone."),
      };
    case "ringing_lead":
      return {
        icon: LucidePhoneCall,
        tone: "text-ink-gray-8",
        title: __("Ringing {0}", name),
        hint: __("Stay on the line."),
      };
    case "on_call":
      return {
        icon: LucidePhone,
        tone: "text-success",
        title: __("On call {0}", elapsed.value),
        hint: __("Talk on your phone. Write notes here."),
      };
    case "ended":
      return box.answered
        ? {
            icon: LucidePhone,
            tone: "text-success",
            title: __("Call ended · {0}", spoken(box.seconds)),
            hint: __("Record how it went."),
          }
        : {
            icon: LucidePhoneMissed,
            tone: "text-warning",
            title: __("Not answered"),
            hint: __("Record the result so the lead is called again."),
          };
    case "timeout":
      return {
        icon: LucidePhoneOff,
        tone: "text-ink-gray-7",
        title: __("Can't see this call any more"),
        hint: __("When you are done, record how it went."),
      };
    default:
      return {
        icon: LucidePhoneOff,
        tone: "text-danger",
        title: __("The call didn't start"),
        hint: box.message,
      };
  }
});

const elapsed = computed(() => callLength((+now.value - box.onCallAt) / 1000));
const pillText = computed(() => (box.phase === "on_call" ? elapsed.value : ""));

// focus follows the box: into it when it opens or grows, onto the pill when it shrinks
async function focusBox() {
  await nextTick();
  (box.minimised ? pill.value : panel.value)?.focus();
}
watch(
  () => [box.open, box.minimised],
  ([open]) => open && focusBox()
);

function collapse() {
  minimise(true);
}
function expand() {
  minimise(false);
}
function onEscape() {
  if (canClose.value) closeBox();
  else collapse();
}

// the incoming notice: asked every 10 seconds while the tab is visible, with a ring that
// plays only where the browser lets it
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
