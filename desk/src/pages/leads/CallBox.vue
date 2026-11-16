<template>
  <IncomingCallNotice />

  <!-- minimised: one small pill that says who, where the call is and how long -->
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
    <span class="shrink-0 text-ink-gray-7">{{ pillText }}</span>
    <span class="shrink-0 font-mono tabular-nums text-ink-gray-7">{{
      timerText
    }}</span>
  </button>

  <section
    v-else-if="box.open"
    ref="panel"
    role="dialog"
    aria-modal="false"
    tabindex="-1"
    :aria-labelledby="titleId"
    :style="panelStyle"
    class="fixed inset-x-0 bottom-0 z-40 flex max-h-[90dvh] flex-col rounded-t-2xl border border-outline-gray-2 bg-surface-base pb-[env(safe-area-inset-bottom)] shadow-lg focus-visible:outline-none sm:inset-x-auto sm:bottom-4 sm:right-4 sm:max-h-[calc(100dvh-2rem)] sm:w-96 sm:rounded-xl sm:pb-0"
    @keydown.esc.stop="collapse"
  >
    <!-- status in plain words and the timer; on a computer this is also the handle to move the box -->
    <header class="flex items-start gap-2 border-b border-outline-gray-2 p-4">
      <div
        ref="handle"
        class="flex min-w-0 flex-1 items-start gap-3"
        :class="isDesktop ? 'cursor-move select-none' : ''"
      >
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
            class="text-xl-medium text-ink-gray-9"
            role="status"
            aria-live="polite"
          >
            {{ status.title }}
          </h2>
          <p v-if="status.hint" class="mt-0.5 text-p-sm text-ink-gray-7">
            {{ status.hint }}
          </p>
        </div>
        <span
          v-if="timerText"
          class="mt-1 shrink-0 font-mono text-base tabular-nums text-ink-gray-7"
          >{{ timerText }}</span
        >
      </div>
      <div class="-mr-2 -mt-1 flex shrink-0 items-center">
        <Button
          v-if="isWaiting(box.phase)"
          class="!size-11"
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
          class="!size-11"
          variant="ghost"
          :aria-label="__('Minimise the call box')"
          @click="collapse"
        >
          <template #icon>
            <LucideMinus class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="canClose"
          class="!size-11"
          variant="ghost"
          :aria-label="__('Close')"
          @click="closeBox()"
        >
          <template #icon>
            <LucideX class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </header>

    <div v-if="box.call" class="flex flex-col gap-4 overflow-y-auto p-4">
      <!-- who is being called -->
      <div class="flex items-start gap-3">
        <CallAvatar :name="box.call.lead_name" />
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <p class="truncate text-lg-medium text-ink-gray-9">
            {{ box.call.lead_name }}
          </p>
          <p v-if="box.call.company" class="truncate text-p-sm text-ink-gray-7">
            {{ box.call.company }}
          </p>
          <div v-if="box.stage" class="mt-1 flex">
            <TaskyBadge
              :label="stageLabel(options, box.stage)"
              :tone="stageTone(options, box.stage)"
              :icon="stageIcon(box.stage)"
            />
          </div>
        </div>
      </div>
      <p v-if="box.call.product" class="text-p-sm text-ink-gray-8">
        {{ __("Calling for: {0}", box.call.product) }}
        <template v-if="box.call.intro"> — {{ box.call.intro }}</template>
      </p>
      <div v-if="box.number" class="flex flex-col">
        <span class="font-mono text-xl tabular-nums text-ink-gray-9">{{
          box.number
        }}</span>
        <span v-if="dialledAbout" class="text-p-sm text-ink-gray-6">{{
          dialledAbout
        }}</span>
      </div>

      <!-- no hang-up button: the call is on the phone, and only the phone can end it -->
      <p
        v-if="onPhone"
        class="flex items-center gap-2 rounded-lg bg-surface-gray-2 px-3 py-3 text-base-medium text-ink-gray-9"
      >
        <LucidePhone class="size-5 shrink-0" aria-hidden="true" />
        {{ __("To end the call, hang up on your phone.") }}
      </p>

      <!-- the controls row: what the person can do about the call itself -->
      <div
        v-if="canStopWaiting || canAskResult || box.phase === 'refused'"
        class="flex flex-wrap gap-2"
      >
        <Button
          v-if="box.phase === 'refused'"
          class="!h-12"
          variant="solid"
          :label="__('Try again')"
          @click="box.call && placeCall(box.call)"
        />
        <Button
          v-if="canStopWaiting"
          class="!h-12"
          variant="outline"
          :label="__('Stop waiting')"
          :tooltip="__('Your phone never rang, or you dialled by mistake')"
          @click="stopWaiting()"
        />
        <Button
          v-if="canAskResult"
          class="!h-12"
          variant="outline"
          :label="__('Record the result')"
          @click="askResult()"
        />
      </div>

      <p
        v-if="box.phase === 'ended' && box.answered && recordingNote"
        class="flex flex-wrap items-center gap-x-2 gap-y-1 text-p-sm text-ink-gray-8"
      >
        <LucideAudioLines
          class="size-4 shrink-0 text-ink-gray-6"
          aria-hidden="true"
        />
        <span>{{ recordingNote }}</span>
        <router-link
          v-if="box.recording === 'saved'"
          class="inline-flex min-h-11 items-center rounded underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :to="{
            name: 'Lead',
            params: { leadId: box.call.lead },
            hash: `#call-${box.callName}`,
          }"
          >{{ __("Listen on the lead") }}</router-link
        >
      </p>

      <!-- the result, right here -->
      <section
        v-if="awaitingResult"
        class="flex flex-col gap-3"
        :aria-label="__('How did the call go?')"
      >
        <h3 class="text-base-medium text-ink-gray-9">
          {{ __("How did the call go?") }}
        </h3>
        <CallOutcomeChoices
          v-model:note="box.note"
          :saving="box.saving"
          :reset-key="box.referenceId"
          @answer="saveResult"
          @dismiss="dismissResult"
        />
      </section>

      <!-- the result is in -->
      <section v-else-if="box.recorded" class="flex flex-col gap-3">
        <p
          role="status"
          class="flex items-center gap-2 text-base-medium text-ink-gray-9"
        >
          <LucideCircleCheck
            class="size-5 shrink-0 text-success"
            aria-hidden="true"
          />
          {{ recordedText }}
        </p>
        <Button
          v-if="box.call.item && box.next !== null"
          class="!h-12 w-full"
          variant="solid"
          :loading="box.next === undefined"
          :disabled="box.next === undefined"
          @click="goToNext()"
        >
          <template #prefix>
            <LucideArrowRight class="size-4" aria-hidden="true" />
          </template>
          {{
            box.next
              ? __("Next call: {0}", box.next.name)
              : __("Finding the next call…")
          }}
        </Button>
        <p
          v-else-if="box.call.item && box.recorded === 'result'"
          class="text-p-sm text-ink-gray-7"
        >
          {{ __("That was the last call waiting in Today's calls.") }}
        </p>
        <Button
          class="!h-12 w-full"
          variant="outline"
          :label="__('Close')"
          @click="closeBox()"
        />
      </section>

      <!-- a note while the call is on -->
      <template v-else-if="box.phase !== 'refused' && !awaitingResult">
        <FormControl
          v-model="box.note"
          type="textarea"
          :label="__('Note for this call')"
          :rows="3"
          maxlength="500"
        />
        <p class="-mt-3 text-p-sm text-ink-gray-6">
          {{
            __("It goes into how the call went, when you record the result.")
          }}
        </p>
      </template>

      <CallBoxNumbers
        :numbers="box.numbers && usableNumbers"
        :in-progress="isWaiting(box.phase) || box.phase === 'on_call'"
        :can-dial="canDialAnother"
        :hint="
          notConnected && !box.recorded
            ? __('Not reached? Try another number.')
            : ''
        "
        @dial="tryNumber"
        @add="showAdd = true"
      />

      <CallBoxRecent :calls="box.recent" />

      <router-link
        class="inline-flex min-h-11 items-center gap-1 self-start rounded text-p-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :to="{ name: 'Lead', params: { leadId: box.call.lead } }"
      >
        <LucideExternalLink class="size-3.5" aria-hidden="true" />
        {{ __("Open the lead") }}
      </router-link>
    </div>
  </section>

  <AddNumberDialog
    v-if="box.call"
    v-model:open="showAdd"
    :lead-id="box.call.lead"
    on-call
    @saved="loadLead(true)"
  />
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { ringMuted } from "@/composables/ringTone";
import { __ } from "@/translation";
import {
  useDraggable,
  useLocalStorage,
  useMediaQuery,
  useNow,
  useWindowSize,
} from "@vueuse/core";
import { Button, FormControl } from "frappe-ui";
import { computed, nextTick, ref, useId, watch } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideAudioLines from "~icons/lucide/audio-lines";
import LucideCircleCheck from "~icons/lucide/circle-check";
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
import AddNumberDialog from "./AddNumberDialog.vue";
import { OUTCOMES } from "./callBatches";
import {
  askResult,
  awaitingResult,
  box,
  canClose,
  canDialAnother,
  closeBox,
  dismissResult,
  goToNext,
  isDialled,
  isWaiting,
  loadLead,
  minimise,
  notConnected,
  placeCall,
  RECORD_AFTER_MS,
  saveResult,
  stopWaiting,
  usableNumbers,
} from "./callBox";
import CallAvatar from "./CallAvatar.vue";
import CallBoxNumbers from "./CallBoxNumbers.vue";
import CallBoxRecent from "./CallBoxRecent.vue";
import CallOutcomeChoices from "./CallOutcomeChoices.vue";
import IncomingCallNotice from "./IncomingCallNotice.vue";
import {
  callLength,
  leadOptions,
  loadLeadOptions,
  stageIcon,
  stageLabel,
  stageTone,
  type LeadNumber,
  type LeadOptions,
} from "./leads";

const titleId = useId();
const panel = ref<HTMLElement | null>(null);
const pill = ref<HTMLElement | null>(null);
const handle = ref<HTMLElement | null>(null);
const showAdd = ref(false);

loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);

// the clock runs only while the box is open
const now = useNow({ interval: 1000, controls: false });

const over = computed(
  () =>
    box.phase === "ended" || box.phase === "timeout" || box.phase === "stopped"
);
/** without live updates the box can't tell the call is over: offer the result anyway */
const tooLong = computed(
  () =>
    isWaiting(box.phase) &&
    box.phase !== "placing" &&
    +now.value - box.startedAt > RECORD_AFTER_MS
);
const canStopWaiting = computed(
  () => isWaiting(box.phase) && box.phase !== "placing" && !box.recorded
);
const canAskResult = computed(
  () => tooLong.value && !box.resultAsked && !box.recorded
);
/** the call is on and only the phone can end it */
const onPhone = computed(
  () => (isWaiting(box.phase) || box.phase === "on_call") && !box.recorded
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
        hint: __("Your phone rings first, then {0}.", name),
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
        title: __("On call"),
        hint: __("Talk on your phone. Write notes here."),
      };
    case "ended":
      return box.answered
        ? {
            icon: LucidePhone,
            tone: "text-success",
            title: __("Call ended · {0}", spoken(box.seconds)),
            hint: box.recorded ? "" : __("Record how it went."),
          }
        : {
            icon: LucidePhoneMissed,
            tone: "text-warning",
            title: __("Not answered"),
            hint: box.recorded
              ? ""
              : __("Record the result so the lead is called again."),
          };
    case "stopped":
      return {
        icon: LucidePhoneOff,
        tone: "text-ink-gray-7",
        title: __("Stopped waiting"),
        hint: box.recorded
          ? ""
          : __(
              "Record the result, or say it was a mistake. If the call did connect, it still shows on the lead."
            ),
      };
    case "timeout":
      return {
        icon: LucidePhoneOff,
        tone: "text-ink-gray-7",
        title: __("Can't see this call any more"),
        hint: box.recorded ? "" : __("When you are done, record how it went."),
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

const recordingNote = computed(() =>
  box.recording === "saved"
    ? __("Recording saved.")
    : box.recording === "pending"
    ? __("Recording is being saved…")
    : ""
);

const recordedText = computed(() =>
  box.recorded === "dismissed"
    ? __("Taken off your list.")
    : __(
        "Saved: {0}",
        OUTCOMES.find((o) => o.value === box.outcome)?.label ?? ""
      )
);

/** "Decision-maker · Anil" for the number being called */
const dialledAbout = computed(() => {
  const found: LeadNumber | undefined = box.numbers?.find(isDialled);
  return found ? [found.label, found.person].filter(Boolean).join(" · ") : "";
});

/** The timer: talk time on a call, the wait while it connects, nothing once it is over. */
const timerText = computed(() => {
  if (box.phase === "on_call")
    return callLength((+now.value - box.onCallAt) / 1000);
  if (isWaiting(box.phase) && box.phase !== "placing")
    return callLength((+now.value - box.startedAt) / 1000);
  return "";
});
const pillText = computed(() =>
  awaitingResult.value && over.value ? __("Add the result") : status.value.title
);

/** The same lead, another of its numbers: the box shows the new call. */
function tryNumber(n: LeadNumber) {
  if (!box.call) return;
  placeCall(
    { ...box.call, number: n.number, phone: n.number, numbers: box.numbers },
    true
  );
}

// ---------- where the box sits ----------

// on a computer it can be moved, and stays where it was put on that device; on a phone it is
// a sheet at the bottom
const PANEL_WIDTH = 384;
const isDesktop = useMediaQuery("(min-width: 640px)");
const { width, height } = useWindowSize();
const saved = useLocalStorage("call-box-position", { x: -1, y: -1 });
const { x, y } = useDraggable(panel, {
  handle,
  initialValue: { ...saved.value },
  preventDefault: true,
  disabled: computed(() => !isDesktop.value),
  onEnd: (position) => {
    saved.value = { x: position.x, y: position.y };
  },
});
const panelStyle = computed(() => {
  if (!isDesktop.value || x.value < 0) return undefined;
  const clamp = (value: number, min: number, max: number) =>
    Math.min(Math.max(value, min), Math.max(min, max));
  return {
    left: `${clamp(x.value, 8, width.value - PANEL_WIDTH - 8)}px`,
    top: `${clamp(y.value, 8, height.value - 160)}px`,
    right: "auto",
    bottom: "auto",
  };
});

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
</script>
