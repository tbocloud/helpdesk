<template>
  <Dialog
    :open="open"
    :title="title"
    size="md"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p v-if="call" class="text-p-sm text-ink-gray-7">
        {{ call.summary.lead_name || call.lead }}
        <template v-if="call.summary.company_name">
          · {{ call.summary.company_name }}
        </template>
      </p>

      <!-- Connected: what was said, and where the lead goes now -->
      <template v-if="mode === 'Connected'">
        <FormControl
          v-model="note"
          type="textarea"
          :label="__('What was said')"
          :rows="3"
          maxlength="500"
        />
        <FormControl
          v-model="stage"
          type="select"
          :label="__('Move the lead to')"
          :options="stageOptions"
        />
        <FormControl
          v-model="followUp"
          type="datetime-local"
          :label="__('Follow up on (optional)')"
          :min="nowLocal()"
        />
      </template>

      <!-- Call back: when -->
      <template v-else-if="mode === 'Call back'">
        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("Call back") }}
          </legend>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="preset in PRESETS"
              :key="preset.label"
              type="button"
              size="md"
              variant="outline"
              :label="preset.label"
              :aria-pressed="callbackAt === preset.value()"
              @click="callbackAt = preset.value()"
            />
          </div>
        </fieldset>
        <FormControl
          v-model="callbackAt"
          type="datetime-local"
          :label="__('Call back at')"
          :min="nowLocal()"
          required
        />
        <FormControl
          v-model="note"
          type="textarea"
          :label="__('Note (optional)')"
          :rows="2"
          maxlength="500"
        />
      </template>

      <!-- Not interested: why, and whether to close the lead -->
      <template v-else-if="mode === 'Not interested'">
        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("Why not?") }}
          </legend>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="reason in REASONS"
              :key="reason"
              type="button"
              size="md"
              variant="outline"
              :label="reason"
              :aria-pressed="note === reason"
              @click="note = reason"
            />
          </div>
        </fieldset>
        <FormControl
          v-model="note"
          type="textarea"
          :label="__('Reason')"
          :rows="2"
          maxlength="500"
          required
        />
        <Switch
          v-model="closeLost"
          :label="__('Close this lead as lost')"
          :description="
            __('Leave it off to keep the lead open and only log the call.')
          "
        />
      </template>

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="emit('update:open', false)" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="submitLabel"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, FormControl, Switch } from "frappe-ui";
import { dayjs } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type { CallOutcome, QueueCall } from "./callBatches";
import type { LeadStage } from "./leads";

export interface OutcomeAnswer {
  outcome: CallOutcome;
  note: string;
  /** "YYYY-MM-DD HH:mm:ss", as the ERP site takes it */
  callback_at: string | null;
  /** a stage to move the lead to after the call is saved */
  stage: string | null;
}

const props = defineProps<{
  open: boolean;
  mode: "Connected" | "Call back" | "Not interested" | null;
  call: QueueCall | null;
  stages: LeadStage[];
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "answer", value: OutcomeAnswer): void;
}>();

const LOCAL = "YYYY-MM-DDTHH:mm";
const PRESETS = [
  {
    label: __("In 1 hour"),
    value: () => dayjs().add(1, "hour").format(LOCAL),
  },
  {
    label: __("In 2 hours"),
    value: () => dayjs().add(2, "hour").format(LOCAL),
  },
  {
    label: __("Tomorrow 10:00"),
    value: () => dayjs().add(1, "day").hour(10).minute(0).format(LOCAL),
  },
];
const REASONS = [
  __("Not needed"),
  __("Too expensive"),
  __("Uses someone else"),
  __("Not now"),
];
// the lead stage that ends a lead badly; the ERP site wants a reason for it
const LOST_FALLBACK = "Closed – Lost";

const formId = `call-outcome-${useId()}`;
const note = ref("");
const stage = ref("");
const followUp = ref("");
const callbackAt = ref("");
const closeLost = ref(false);
const errorMessage = ref("");

const title = computed(
  () =>
    ({
      Connected: __("They picked up"),
      "Call back": __("Call back later"),
      "Not interested": __("Not interested"),
    }[props.mode || "Connected"])
);
const submitLabel = computed(() =>
  props.mode === "Not interested" && closeLost.value
    ? __("Save and close lead")
    : __("Save call")
);

const lostStage = computed(
  () =>
    props.stages.find((s) => (s.type || "").toLowerCase() === "lost")?.name ||
    LOST_FALLBACK
);
const stageOptions = computed(() =>
  props.stages.map((s) => ({ label: s.label || s.name, value: s.name }))
);

function nowLocal() {
  return dayjs().format(LOCAL);
}

// each time it opens it starts empty, on the lead's own stage
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    note.value = followUp.value = callbackAt.value = errorMessage.value = "";
    closeLost.value = false;
    stage.value = props.call?.summary.stage || "";
  }
);

function erpTime(local: string) {
  return local ? dayjs(local).format("YYYY-MM-DD HH:mm:ss") : null;
}

function submit() {
  const outcome = props.mode;
  if (!outcome) return;
  errorMessage.value = "";
  const text = note.value.trim();
  let moveTo: string | null = null;
  let when: string | null = null;
  if (outcome === "Call back") {
    if (!callbackAt.value || dayjs(callbackAt.value).isBefore(dayjs())) {
      errorMessage.value = __("Pick a time in the future to call back.");
      return;
    }
    when = erpTime(callbackAt.value);
  } else if (outcome === "Connected") {
    if (followUp.value) {
      if (dayjs(followUp.value).isBefore(dayjs())) {
        errorMessage.value = __("The follow-up has to be in the future.");
        return;
      }
      when = erpTime(followUp.value);
    }
    if (stage.value && stage.value !== props.call?.summary.stage)
      moveTo = stage.value;
    if (moveTo === lostStage.value && !text) {
      errorMessage.value = __("Say why the lead was lost.");
      return;
    }
  } else if (outcome === "Not interested") {
    if (!text) {
      errorMessage.value = __("Give a reason.");
      return;
    }
    if (closeLost.value) moveTo = lostStage.value;
  }
  emit("answer", { outcome, note: text, callback_at: when, stage: moveTo });
  emit("update:open", false);
}
</script>
