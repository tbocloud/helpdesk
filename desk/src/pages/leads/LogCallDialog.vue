<template>
  <Dialog
    :open="open"
    :title="__('Log a call')"
    size="md"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "For a call you made outside MyOperator. It counts in today's report."
          )
        }}
      </p>
      <fieldset class="flex flex-col gap-2">
        <legend class="mb-1 text-xs text-ink-gray-5">
          {{ __("How did it go?") }}
        </legend>
        <div class="grid grid-cols-2 gap-2">
          <Button
            v-for="choice in OUTCOMES"
            :key="choice.value"
            type="button"
            size="md"
            :variant="outcome === choice.value ? 'solid' : 'outline'"
            :label="choice.label"
            :aria-pressed="outcome === choice.value"
            @click="outcome = choice.value"
          >
            <template #prefix>
              <component
                :is="OUTCOME_LOOK[choice.value].icon"
                class="size-4"
                aria-hidden="true"
              />
            </template>
          </Button>
        </div>
      </fieldset>
      <FormControl
        v-if="outcome === 'Call back'"
        v-model="callbackAt"
        type="datetime-local"
        :label="__('Call back at')"
        :min="nowLocal()"
        required
      />
      <p v-else-if="outcome" class="text-p-sm text-ink-gray-6">
        {{ hint }}
      </p>
      <FormControl
        v-model="note"
        type="textarea"
        :label="__('Note (optional)')"
        :rows="3"
        maxlength="500"
      />
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="emit('update:open', false)" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Log call')"
          :disabled="!outcome"
          :loading="logCall.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, FormControl, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { OUTCOME_LOOK, OUTCOMES, type CallOutcome } from "./callBatches";
import { useLogCall } from "./leads";

const props = defineProps<{ open: boolean; leadId: string }>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "logged"): void;
}>();

// the same six answers as Today's calls; the ERP site moves the lead's stage from them
const HINTS: Record<CallOutcome, string> = {
  Connected: __("A new lead becomes Contacted."),
  "Not answered": __("The lead becomes Not Responding: call again."),
  Busy: __("The lead becomes Not Responding: call again."),
  "Call back": __("The lead becomes Follow-up Required."),
  "Not interested": __("The lead becomes Not Interested."),
  "Wrong number": __("The lead becomes Wrong Number."),
};
const LOCAL = "YYYY-MM-DDTHH:mm";

const formId = `log-call-${useId()}`;
const outcome = ref<CallOutcome | "">("");
const note = ref("");
const callbackAt = ref("");
const logCall = useLogCall();
const hint = computed(() => (outcome.value ? HINTS[outcome.value] : ""));

function nowLocal() {
  return dayjs().format(LOCAL);
}

// each time it opens it starts empty
watch(
  () => props.open,
  (open) => {
    if (open) {
      outcome.value = "";
      note.value = callbackAt.value = "";
    }
  }
);

function submit() {
  if (!outcome.value) return;
  if (
    outcome.value === "Call back" &&
    (!callbackAt.value || dayjs(callbackAt.value).isBefore(dayjs()))
  ) {
    toast.error(__("Pick a time in the future to call back."));
    return;
  }
  logCall.submit(
    {
      lead: props.leadId,
      outcome: outcome.value,
      note: note.value,
      callback_at:
        outcome.value === "Call back"
          ? dayjs(callbackAt.value).format("YYYY-MM-DD HH:mm:ss")
          : null,
    },
    {
      onSuccess() {
        toast.success(__("Call logged"));
        emit("update:open", false);
        emit("logged");
      },
      onError(e: unknown) {
        toast.error(errorText(e, __("Couldn't log the call. Try again.")));
      },
    }
  );
}
</script>
