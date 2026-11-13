<template>
  <!-- the reminder stays on every Leads screen until each call has a result -->
  <div
    v-if="pendingCalls.length && !showSheet"
    class="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
  >
    <div
      role="status"
      class="pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-xl border border-warning bg-surface-base px-4 py-3 shadow-lg"
    >
      <LucidePhoneCall
        class="size-5 shrink-0 text-warning"
        aria-hidden="true"
      />
      <p class="min-w-0 flex-1 text-sm text-ink-gray-9">
        {{
          pendingCalls.length === 1
            ? __("You have 1 call without a result")
            : __(
                "You have {0} calls without a result",
                String(pendingCalls.length)
              )
        }}
      </p>
      <Button
        variant="solid"
        :label="__('Add results')"
        @click="open(pendingCalls[0].lead)"
      />
    </div>
  </div>

  <CallResultSheet
    v-model:open="showSheet"
    :call="current"
    :position="index + 1"
    :total="pendingCalls.length"
    :saving="saving"
    @answer="answer"
    @dismiss="dismiss"
    @add-number="showAddNumber = true"
  />
  <AddNumberDialog
    v-if="current"
    v-model:open="showAddNumber"
    :lead-id="current.lead"
    on-call
  />
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDocumentVisibility, useWindowFocus } from "@vueuse/core";
import { Button, call as post, toast } from "frappe-ui";
import { computed, onMounted, ref, watch } from "vue";
import LucidePhoneCall from "~icons/lucide/phone-call";
import type { CallOutcome } from "./callBatches";
import AddNumberDialog from "./AddNumberDialog.vue";
import CallResultSheet from "./CallResultSheet.vue";
import {
  askFor,
  cameBack,
  dismissCall,
  loadPendingCalls,
  pendingCalls,
  queueChanged,
  type PendingCall,
} from "./pendingCalls";

const showSheet = ref(false);
const showAddNumber = ref(false);
const saving = ref(false);
// the call the sheet is on; after it is saved the next one without a result follows
const currentLead = ref("");
const index = computed(() =>
  Math.max(
    pendingCalls.value.findIndex((c) => c.lead === currentLead.value),
    0
  )
);
const current = computed<PendingCall | null>(
  () => pendingCalls.value[index.value] ?? null
);

onMounted(loadPendingCalls);

function open(lead: string) {
  currentLead.value = lead;
  showSheet.value = true;
}

// coming back to the page after a call: ask how it went
const visibility = useDocumentVisibility();
const focused = useWindowFocus();
watch(visibility, (state) => state === "visible" && cameBack());
watch(focused, (state) => state && cameBack());

watch(askFor, (lead) => {
  if (!lead) return;
  askFor.value = "";
  // the list is read again on coming back: wait for it before looking the lead up
  loadPendingCalls().finally(() => {
    if (pendingCalls.value.some((c) => c.lead === lead)) open(lead);
  });
});

/** The ERP site records it as the person's answer on the call in Today's calls, or logs it on
 * the lead; either way the call stops waiting. */
function answer(
  pending: PendingCall,
  value: { outcome: CallOutcome; note: string; callback_at: string | null }
) {
  saving.value = true;
  const request = pending.item
    ? post("helpdesk.api.call_batches.record_call_outcome", {
        batch_item: pending.item,
        lead: pending.lead,
        outcome: value.outcome,
        note: value.note || null,
        callback_at: value.callback_at,
        number: pending.number,
      })
    : post("helpdesk.api.leads.log_call", {
        lead: pending.lead,
        outcome: value.outcome,
        note: value.note,
        callback_at: value.callback_at,
        number: pending.number,
      });
  request
    .then(() => {
      toast.success(__("Saved"));
      if (pending.item) queueChanged.value++;
      return next();
    })
    .catch((e: unknown) =>
      toast.error(errorText(e, __("Couldn't save the result. Try again.")))
    )
    .finally(() => (saving.value = false));
}

function dismiss(pending: PendingCall, reason: string) {
  saving.value = true;
  dismissCall(pending.lead, reason)
    .then(next)
    .catch((e: unknown) =>
      toast.error(errorText(e, __("Couldn't remove it. Try again.")))
    )
    .finally(() => (saving.value = false));
}

/** On to the next call without a result, or done. */
async function next() {
  await loadPendingCalls();
  const left = pendingCalls.value;
  if (!left.length) {
    showSheet.value = false;
    toast.success(__("All your calls have a result"));
    return;
  }
  currentLead.value = left[Math.min(index.value, left.length - 1)].lead;
}
</script>
