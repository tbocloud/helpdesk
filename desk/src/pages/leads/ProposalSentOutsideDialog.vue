<template>
  <!-- a proposal made and sent by hand (Word, email): recorded with the file that went
       (docs/proposals.md, Sent outside the system) -->
  <Dialog
    :open="open"
    size="md"
    :title="__('Proposal sent outside the system')"
    @update:open="(value: boolean) => !value && close()"
  >
    <form class="flex flex-col gap-4" @submit.prevent="submit">
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "For a proposal you made and sent yourself. The file is kept on the lead, the lead moves to Proposal Sent and the next document opens."
          )
        }}
      </p>
      <div class="flex flex-col gap-1.5">
        <span :id="fileLabelId" class="text-xs text-ink-gray-5">
          {{ __("The proposal that was sent (required)") }}
        </span>
        <div
          v-if="file"
          class="flex min-h-[44px] items-center gap-2 rounded-lg border border-outline-gray-2 px-3"
        >
          <LucidePaperclip
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">{{
            file.name
          }}</span>
          <Button
            variant="ghost"
            :aria-label="__('Remove {0}', file.name)"
            :disabled="save.loading"
            @click="file = null"
          >
            <template #icon>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <Button
          v-else
          class="self-start"
          :label="__('Choose file')"
          :aria-describedby="fileLabelId"
          @click="picker?.click()"
        >
          <template #prefix>
            <LucidePaperclip class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <input
          ref="picker"
          type="file"
          :accept="LEAD_FILE_ACCEPT"
          class="hidden"
          tabindex="-1"
          aria-hidden="true"
          @change="pick"
        />
        <p class="text-p-xs text-ink-gray-5">
          {{
            __(
              "PDF, Word, Excel, PowerPoint, CSV, text, pictures or ZIP, up to 10 MB."
            )
          }}
        </p>
      </div>
      <FormControl
        v-model="note"
        type="textarea"
        :label="__('Note (optional)')"
        :placeholder="__('e.g. Sent by email to the director on 20 Nov')"
        :rows="2"
        maxlength="500"
      />
      <ErrorMessage v-if="error" :message="error" role="alert" />
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button :label="__('Cancel')" :disabled="save.loading" @click="close" />
        <Button
          type="submit"
          variant="solid"
          :label="__('Mark as sent')"
          :loading="save.loading"
          :disabled="!file"
        />
      </div>
    </form>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { ref, useId, watch } from "vue";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideX from "~icons/lucide/x";
import { attachable, LEAD_FILE_ACCEPT } from "./leadFiles";
import { readBase64 } from "./place";
import type { DocumentChain } from "./proposals";

const props = defineProps<{ leadId: string }>();
const open = defineModel<boolean>("open", { required: true });
const emit = defineEmits<{
  /** recorded on the ERP site: the lead's chain as it is now */
  saved: [chain: DocumentChain];
}>();

const fileLabelId = `sent-outside-file-${useId()}`;
const picker = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null);
const note = ref("");
const error = ref("");

watch(open, (value) => {
  if (!value) return;
  file.value = null;
  note.value = "";
  error.value = "";
});

function pick(event: Event) {
  const input = event.target as HTMLInputElement;
  const chosen = input.files?.[0];
  input.value = "";
  if (!chosen) return;
  if (!attachable(chosen)) {
    error.value = __(
      "{0} can't be attached: only PDF, Word, Excel, PowerPoint, CSV, text, pictures or ZIP of at most 10 MB.",
      chosen.name
    );
    return;
  }
  error.value = "";
  file.value = chosen;
}

function close() {
  if (!save.loading) open.value = false;
}

const save = createResource({
  url: "helpdesk.api.proposals.mark_sent_outside",
  method: "POST",
  onSuccess(chain: DocumentChain) {
    toast.success(__("Proposal marked as sent"));
    open.value = false;
    emit("saved", chain);
  },
  onError(e: unknown) {
    error.value = errorText(e, __("Couldn't mark it as sent. Try again."));
  },
});

async function submit() {
  if (!file.value || save.loading) return;
  error.value = "";
  let content: string;
  try {
    content = await readBase64(file.value);
  } catch {
    error.value = __("Couldn't read {0}. Choose it again.", file.value.name);
    return;
  }
  save.submit({
    lead: props.leadId,
    filename: file.value.name,
    content,
    note: note.value.trim(),
  });
}
</script>
