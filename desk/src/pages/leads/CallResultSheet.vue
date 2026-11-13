<template>
  <Dialog
    :open="open"
    :title="__('How did the call go?')"
    size="md"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <div v-if="call" class="flex flex-col gap-4">
      <div class="flex flex-col gap-0.5">
        <p class="text-lg-medium text-ink-gray-9">{{ call.lead_name }}</p>
        <p
          v-if="call.phone"
          class="font-mono text-sm tabular-nums text-ink-gray-7"
        >
          {{ call.phone }}
        </p>
        <button
          type="button"
          class="mt-0.5 inline-flex min-h-8 items-center gap-1 self-start rounded text-p-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          @click="emit('addNumber', call)"
        >
          <LucidePlus class="size-3.5" aria-hidden="true" />
          {{ __("Got another number?") }}
        </button>
        <p
          v-if="total > 1"
          class="text-p-sm tabular-nums text-ink-gray-6"
          aria-live="polite"
        >
          {{
            __(
              "Call {0} of {1} without a result",
              String(position),
              String(total)
            )
          }}
        </p>
      </div>

      <!-- step 1: one big button for each answer -->
      <div
        v-if="step === 'result'"
        class="grid grid-cols-2 gap-3"
        role="group"
        :aria-label="__('How did the call go?')"
      >
        <button
          v-for="choice in CHOICES"
          :key="choice.value"
          type="button"
          class="flex min-h-16 flex-col items-center justify-center gap-1 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2 text-base-medium text-ink-gray-9 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:opacity-60"
          :disabled="saving"
          @click="choose(choice.value)"
        >
          <component :is="choice.icon" class="size-5" aria-hidden="true" />
          {{ choice.label }}
        </button>
      </div>

      <!-- Call back: when -->
      <div v-else-if="step === 'Call back'" class="flex flex-col gap-3">
        <p class="text-sm text-ink-gray-7">{{ __("Call them back…") }}</p>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <button
            v-for="when in WHEN"
            :key="when.label"
            type="button"
            :class="BIG"
            :disabled="saving"
            @click="save('Call back', note, when.at())"
          >
            {{ when.label }}
          </button>
        </div>
      </div>

      <!-- Not interested: why -->
      <div v-else-if="step === 'Not interested'" class="flex flex-col gap-3">
        <p class="text-sm text-ink-gray-7">{{ __("Why not?") }}</p>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="reason in WHY"
            :key="reason"
            type="button"
            :class="BIG"
            :disabled="saving"
            @click="save('Not interested', reason, null)"
          >
            {{ reason }}
          </button>
        </div>
      </div>

      <FormControl
        v-if="step === 'result'"
        v-model="note"
        type="textarea"
        :label="__('Note (optional)')"
        :rows="2"
        maxlength="500"
      />
      <Button
        v-else
        class="self-start"
        variant="ghost"
        :label="__('Back')"
        @click="step = 'result'"
      />

      <!-- not a real call: say why, and it leaves the list -->
      <div
        v-if="step === 'result'"
        class="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-outline-gray-2 pt-3"
      >
        <span class="text-p-sm text-ink-gray-6">{{
          __("Not a real call?")
        }}</span>
        <Button
          v-for="reason in DISMISS_REASONS"
          :key="reason.value"
          variant="ghost"
          size="sm"
          :label="reason.label"
          :disabled="saving"
          @click="emit('dismiss', call, reason.value)"
        />
      </div>
    </div>
    <template #actions>
      <div class="flex justify-end">
        <Button :label="__('Later')" @click="emit('update:open', false)" />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, FormControl } from "frappe-ui";
import { ref, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import { OUTCOME_LOOK, OUTCOMES, type CallOutcome } from "./callBatches";
import {
  callBackIn,
  callBackTomorrow,
  DISMISS_REASONS,
  type PendingCall,
} from "./pendingCalls";

const props = defineProps<{
  open: boolean;
  call: PendingCall | null;
  /** which of the calls without a result this is, and how many there are */
  position: number;
  total: number;
  saving: boolean;
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (
    e: "answer",
    call: PendingCall,
    value: { outcome: CallOutcome; note: string; callback_at: string | null }
  ): void;
  (e: "dismiss", call: PendingCall, reason: string): void;
  (e: "addNumber", call: PendingCall): void;
}>();

// the big buttons; the plain answers save at once, Call back and Not interested ask one more thing
const CHOICES = OUTCOMES.map((o) => ({
  ...o,
  icon: OUTCOME_LOOK[o.value].icon,
}));
const BIG =
  "flex min-h-14 items-center justify-center rounded-xl border border-outline-gray-2 bg-surface-base px-3 text-base-medium text-ink-gray-9 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:opacity-60";
const WHEN = [
  { label: __("In 1 hour"), at: () => callBackIn(1) },
  { label: __("In 2 hours"), at: () => callBackIn(2) },
  { label: __("Tomorrow 10:00"), at: callBackTomorrow },
];
const WHY = [
  __("Not needed"),
  __("Too expensive"),
  __("Uses someone else"),
  __("Not now"),
];

const step = ref<"result" | "Call back" | "Not interested">("result");
const note = ref("");

// each call starts on the six buttons with an empty note
watch(
  () => [props.open, props.call?.lead],
  () => {
    step.value = "result";
    note.value = "";
  }
);

function choose(outcome: CallOutcome) {
  if (outcome === "Call back" || outcome === "Not interested")
    step.value = outcome;
  else save(outcome, note.value, null);
}

function save(outcome: CallOutcome, text: string, callback_at: string | null) {
  if (props.call)
    emit("answer", props.call, { outcome, note: text.trim(), callback_at });
}
</script>
