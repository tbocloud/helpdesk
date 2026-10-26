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
          />
        </div>
      </fieldset>
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
import { Button, Dialog, FormControl, toast } from "frappe-ui";
import { ref, useId, watch } from "vue";
import { useLogCall } from "./leads";

const props = defineProps<{ open: boolean; leadId: string }>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "logged"): void;
}>();

const OUTCOMES = [
  { value: "Connected", label: __("Connected") },
  { value: "No answer", label: __("No answer") },
  { value: "Busy", label: __("Busy") },
  { value: "Voicemail", label: __("Voicemail") },
];

const formId = `log-call-${useId()}`;
const outcome = ref("");
const note = ref("");
const logCall = useLogCall();

// each time it opens it starts empty
watch(
  () => props.open,
  (open) => {
    if (open) outcome.value = note.value = "";
  }
);

function submit() {
  if (!outcome.value) return;
  logCall.submit(
    { lead: props.leadId, outcome: outcome.value, note: note.value },
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
