<template>
  <!-- edits in words: each message is one small structured change on the ERP site -->
  <details
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :open="open"
    @toggle="open = ($event.target as HTMLDetailsElement).open"
  >
    <summary
      class="flex min-h-[44px] cursor-pointer items-center gap-2 px-4 text-base-medium text-ink-gray-9"
    >
      {{ __("Assistant") }}
      <span class="text-p-sm font-normal text-ink-gray-5">{{
        __("e.g. “add Payroll”, “make it 90 days”, “remove AMC”")
      }}</span>
    </summary>
    <div class="flex flex-col gap-3 border-t border-outline-gray-1 p-4">
      <ol
        v-if="chat.length"
        ref="logEl"
        class="flex max-h-72 flex-col gap-2 overflow-y-auto"
        role="log"
        aria-live="polite"
        :aria-label="__('Conversation')"
      >
        <li
          v-for="(m, i) in chat"
          :key="i"
          class="max-w-[85%] rounded-lg px-3 py-2 text-p-sm"
          :class="
            m.role === 'assistant'
              ? 'self-start bg-surface-gray-1 text-ink-gray-8'
              : 'self-end border border-outline-gray-2 text-ink-gray-9'
          "
        >
          <span class="sr-only">{{
            m.role === "assistant" ? __("Assistant:") : __("You:")
          }}</span>
          {{ m.text }}
        </li>
      </ol>
      <p v-if="!ai" class="text-p-sm text-ink-gray-6">
        {{
          __(
            "AI is off on the ERP site: change the form and the sections directly."
          )
        }}
      </p>
      <form v-else class="flex items-end gap-2" @submit.prevent="sendMessage">
        <FormControl
          v-model="message"
          class="flex-1"
          :aria-label="__('A change to make')"
          :placeholder="__('Ask for a change')"
          maxlength="1000"
          :disabled="!editable || edit.loading"
        />
        <Button
          type="submit"
          variant="solid"
          :label="__('Send')"
          :loading="edit.loading"
          :disabled="!editable || !message.trim() || dirty"
          :tooltip="dirty ? __('Save your changes first') : ''"
        >
          <template #icon>
            <LucideArrowUp class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </form>
      <p v-if="error" role="alert" class="text-p-sm text-danger">{{ error }}</p>
    </div>
  </details>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl, toast } from "frappe-ui";
import { nextTick, ref } from "vue";
import LucideArrowUp from "~icons/lucide/arrow-up";
import type { Proposal } from "./proposals";

const props = defineProps<{
  proposal: string;
  chat: { role: "assistant" | "presales"; text: string }[];
  ai: boolean;
  editable: boolean;
  dirty: boolean;
}>();
const emit = defineEmits<{ (e: "changed", value: Proposal): void }>();

const open = ref(false);
const message = ref("");
const error = ref("");
const logEl = ref<HTMLElement>();

const edit = createResource({
  url: "helpdesk.api.proposals.chat_edit",
  method: "POST",
  onSuccess(d: { proposal: Proposal; warnings?: string[] }) {
    message.value = "";
    emit("changed", d.proposal);
    for (const w of d.warnings ?? []) toast.warning(w);
    nextTick(() => logEl.value?.scrollTo({ top: logEl.value.scrollHeight }));
  },
  onError(e: unknown) {
    error.value = errorText(
      e,
      __("Couldn't make that change. Edit it directly.")
    );
  },
});

function sendMessage() {
  if (!message.value.trim() || props.dirty) return;
  error.value = "";
  edit.submit({ name: props.proposal, message: message.value });
}
</script>
