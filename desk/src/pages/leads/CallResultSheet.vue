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

      <CallOutcomeChoices
        v-model:note="note"
        :saving="saving"
        :reset-key="`${open}-${call.lead}`"
        @answer="(value) => emit('answer', call!, value)"
        @dismiss="(reason) => emit('dismiss', call!, reason)"
      />
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
import { Button, Dialog } from "frappe-ui";
import { ref, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import type { CallOutcome } from "./callBatches";
import CallOutcomeChoices from "./CallOutcomeChoices.vue";
import type { PendingCall } from "./pendingCalls";

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

const note = ref("");

watch(
  () => [props.open, props.call?.lead],
  () => {
    note.value = "";
  }
);
</script>
