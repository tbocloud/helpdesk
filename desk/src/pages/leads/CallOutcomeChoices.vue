<template>
  <div class="flex flex-col gap-4">
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
      <form class="flex items-end gap-2" @submit.prevent="saveChosenTime">
        <FormControl
          v-model="chosenTime"
          class="min-w-0 flex-1"
          type="datetime-local"
          :label="__('Or pick a day and time')"
        />
        <Button
          type="submit"
          class="!h-10 shrink-0"
          :label="__('Save')"
          :disabled="saving || !chosenTime"
        />
      </form>
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
      v-if="step === 'result' && !hideNote"
      v-model="note"
      type="textarea"
      :label="__('Note (optional)')"
      :rows="2"
      maxlength="500"
    />
    <Button
      v-else-if="step !== 'result'"
      class="!h-11 self-start"
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
        class="!h-11"
        variant="ghost"
        :label="reason.label"
        :disabled="saving"
        @click="emit('dismiss', reason.value)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
// The six answers to "How did the call go?", shared by the call box and the result sheet:
// the plain answers save at once, Call back and Not interested ask one more thing first.
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import { ref, watch } from "vue";
import { OUTCOME_LOOK, OUTCOMES, type CallOutcome } from "./callBatches";
import {
  callBackIn,
  callBackTomorrow,
  DISMISS_REASONS,
  erpTime,
} from "./pendingCalls";

const props = defineProps<{
  saving: boolean;
  /** the call box shows its own note field while the call is on */
  hideNote?: boolean;
  /** a new call starts on the six buttons again */
  resetKey?: string;
}>();
const note = defineModel<string>("note", { default: "" });
const emit = defineEmits<{
  (
    e: "answer",
    value: { outcome: CallOutcome; note: string; callback_at: string | null }
  ): void;
  (e: "dismiss", reason: string): void;
}>();

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
const chosenTime = ref("");

watch(
  () => props.resetKey,
  () => {
    step.value = "result";
    chosenTime.value = "";
  }
);

function choose(outcome: CallOutcome) {
  if (outcome === "Call back" || outcome === "Not interested")
    step.value = outcome;
  else save(outcome, note.value, null);
}

function saveChosenTime() {
  const when = new Date(chosenTime.value);
  if (!chosenTime.value || Number.isNaN(+when)) return;
  save("Call back", note.value, erpTime(when));
}

function save(outcome: CallOutcome, text: string, callback_at: string | null) {
  emit("answer", { outcome, note: text.trim(), callback_at });
}
</script>
