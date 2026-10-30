<template>
  <!-- the AI drafts a first message for each lead of a prospect run; a person approves each one in Outreach -->
  <Button
    v-if="options?.outreach"
    :label="__('Draft first messages')"
    :size="size"
    @click="open = true"
  >
    <template #prefix>
      <LucideMailPlus class="size-4" aria-hidden="true" />
    </template>
  </Button>

  <Dialog v-model:open="open" :title="__('Draft first messages')" size="lg">
    <div class="flex flex-col gap-4">
      <template v-if="!result">
        <p class="text-p-sm text-ink-gray-7">
          {{
            __(
              "The AI writes a first message for each lead of this run, from what its own website showed. You read, edit and approve each one in Outreach. Nothing is sent until you approve it."
            )
          }}
        </p>
        <div class="flex flex-col gap-1.5">
          <span id="draft-channel" class="text-xs text-ink-gray-6">{{
            __("Channel")
          }}</span>
          <TabButtons
            v-model="channel"
            aria-labelledby="draft-channel"
            :options="CHANNELS"
          />
        </div>
        <p v-if="draft.error" role="alert" class="text-p-sm text-danger">
          {{ errorText(draft.error, __("Couldn't draft the messages.")) }}
        </p>
        <div class="flex justify-end">
          <Button
            variant="solid"
            :label="__('Draft messages')"
            :loading="draft.loading"
            @click="draft.submit({ run, channel })"
          />
        </div>
      </template>

      <template v-else>
        <p role="status" class="text-p-sm text-ink-gray-9">
          {{
            result.queued
              ? __(
                  "{0} drafts are being written. They appear in Outreach in a minute or two.",
                  String(result.queued)
                )
              : __("No drafts were made.")
          }}
        </p>
        <details v-if="result.skipped.length" class="text-p-sm text-ink-gray-7">
          <summary
            class="cursor-pointer rounded text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          >
            {{ __("{0} leads skipped", String(result.skipped.length)) }}
          </summary>
          <ul class="mt-2 flex max-h-48 flex-col gap-1 overflow-auto">
            <li v-for="skipped in result.skipped" :key="skipped.lead">
              <span class="text-ink-gray-9">{{
                skipped.lead_name || skipped.lead
              }}</span>
              · {{ skipped.reason }}
            </li>
          </ul>
        </details>
        <div class="flex justify-end gap-2">
          <Button :label="__('Close')" @click="close" />
          <Button
            variant="solid"
            :label="__('Open Outreach')"
            :route="{ name: 'Leads', query: { view: 'outreach' } }"
          />
        </div>
      </template>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, TabButtons } from "frappe-ui";
import { computed, ref } from "vue";
import LucideMailPlus from "~icons/lucide/mail-plus";
import { leadOptions, loadLeadOptions, type LeadOptions } from "./leads";
import type { DraftResult, OutreachChannel } from "./outreach";

defineProps<{ run: string; size?: "sm" | "md" }>();

loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const CHANNELS = [
  { label: __("Email"), value: "Email" },
  { label: __("WhatsApp"), value: "WhatsApp" },
];

const open = ref(false);
const channel = ref<OutreachChannel>("Email");
const result = ref<DraftResult | null>(null);
const draft = createResource({
  url: "helpdesk.api.outreach.draft_outreach",
  method: "POST",
  onSuccess(data: DraftResult) {
    result.value = data;
  },
});

function close() {
  open.value = false;
  result.value = null;
}
</script>
