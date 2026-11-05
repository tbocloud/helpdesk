<template>
  <!-- the ticket's one box to write in (Phase 16): pick who it is for, then write. A reply goes to
       the customer by email; a note stays in the team; a question to Copilot is answered in the
       conversation and changes nothing on its own -->
  <div
    ref="rootRef"
    class="shrink-0 border-t border-outline-gray-2 bg-surface-base"
  >
    <div
      class="flex items-center gap-1 overflow-x-auto px-3 pt-2 hide-scrollbar sm:px-4"
      role="radiogroup"
      :aria-label="__('Who you\'re writing to')"
    >
      <button
        v-for="m in modes"
        :key="m.mode"
        type="button"
        role="radio"
        :aria-checked="composerMode === m.mode"
        :aria-keyshortcuts="m.key"
        class="inline-flex h-8 shrink-0 max-sm:h-11 [@media(pointer:coarse)]:h-11 items-center gap-1.5 rounded-full px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :class="
          composerMode === m.mode
            ? m.on
            : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9'
        "
        @click="choose(m.mode)"
      >
        <component :is="m.icon" class="size-4" aria-hidden="true" />
        {{ m.label }}
        <kbd
          v-if="!isMobileView"
          class="rounded border px-1 font-mono text-2xs opacity-70"
          :class="
            composerMode === m.mode ? 'border-current' : 'border-outline-gray-2'
          "
          aria-hidden="true"
          >{{ m.key.toUpperCase() }}</kbd
        >
      </button>
      <TypingIndicator :ticketId="ticketId" class="ms-auto" />
    </div>

    <!-- a reply to the customer -->
    <div v-show="composerMode === 'reply'" class="px-3 pb-3 pt-2 sm:px-4">
      <div
        v-if="!showEmailBox"
        class="flex items-center gap-1.5 rounded-2xl border-2 border-outline-blue-1 bg-surface-base p-1.5"
      >
        <button
          type="button"
          class="min-w-0 flex-1 truncate rounded-xl px-2.5 py-1.5 text-start text-base text-ink-gray-5 hover:text-ink-gray-7 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          @click="startWriting('reply')"
        >
          {{ __("Write to {0}. They get it by email.", contactFirst) }}
        </button>
        <Button
          v-if="draftReady"
          size="sm"
          :label="__('Use Copilot\'s draft')"
          @click="useDraft"
        >
          <template #prefix>
            <LucideSparkles class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
      <div
        v-show="showEmailBox"
        class="overflow-hidden rounded-2xl border-2 border-outline-blue-1"
        @keydown.ctrl.enter.capture.stop="submitEmail"
        @keydown.meta.enter.capture.stop="submitEmail"
        @keydown.esc.capture.stop="showEmailBox = false"
      >
        <div
          v-if="draftReady"
          class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 bg-info-soft px-4 py-1.5 text-sm text-ink-gray-8"
          role="status"
        >
          <LucideSparkles
            class="size-4 shrink-0 text-info"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1">{{
            __("Copilot drafted a reply from what it found.")
          }}</span>
          <Button size="sm" :label="__('Use the draft')" @click="useDraft" />
          <Button
            size="sm"
            variant="ghost"
            :label="__('Not now')"
            @click="draftDismissed = true"
          />
        </div>
        <EmailEditor
          ref="emailEditorRef"
          :label="
            isMobileView
              ? __('Send')
              : isMac
              ? __('Send (⌘ + ⏎)')
              : __('Send (Ctrl + ⏎)')
          "
          :placeholder="__('Hi {0}, we are looking into this.', contactFirst)"
          :ticketId="ticketId"
          :to-emails="[doc.raised_by]"
          :cc-emails="[]"
          :bcc-emails="[]"
          @submit="afterSend"
          @discard="showEmailBox = false"
        />
      </div>
    </div>

    <!-- a note for the team -->
    <div v-show="composerMode === 'note'" class="px-3 pb-3 pt-2 sm:px-4">
      <button
        v-if="!showCommentBox"
        type="button"
        class="flex w-full items-center gap-2 rounded-2xl border-2 border-note-border bg-note px-4 py-2.5 text-start text-base text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        @click="startWriting('note')"
      >
        <LucideLock class="size-4 shrink-0" aria-hidden="true" />
        {{
          __("Write a note. Only the team sees it; type @ to mention someone.")
        }}
      </button>
      <div
        v-show="showCommentBox"
        class="overflow-hidden rounded-2xl border-2 border-note-border bg-note"
        @keydown.ctrl.enter.capture.stop="submitComment"
        @keydown.meta.enter.capture.stop="submitComment"
        @keydown.esc.capture.stop="showCommentBox = false"
      >
        <CommentTextEditor
          ref="commentEditorRef"
          :label="
            isMobileView
              ? __('Add note')
              : isMac
              ? __('Add note (⌘ + ⏎)')
              : __('Add note (Ctrl + ⏎)')
          "
          :ticketId="ticketId"
          :editable="showCommentBox"
          doctype="HD Ticket"
          :placeholder="__('@name could you look at this?')"
          @submit="afterSend"
          @discard="showCommentBox = false"
        />
      </div>
    </div>

    <!-- a question to Copilot -->
    <div v-show="composerMode === 'copilot'" class="px-3 pb-3 pt-2 sm:px-4">
      <p
        v-if="!copilot.canWrite.value"
        class="flex items-start gap-2 rounded-2xl border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5 text-sm text-ink-gray-6"
      >
        <LucideLock class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{
          __(
            "Only the developer the ticket is assigned to, its project coordinators and admins can write to Copilot here. You can read what it says."
          )
        }}
      </p>
      <form
        v-else
        class="rounded-2xl border-2 border-outline-gray-3 bg-surface-gray-1"
        @submit.prevent="ask()"
      >
        <div v-if="files.length" class="flex flex-wrap gap-1 px-3 pt-2">
          <span
            v-for="f in files"
            :key="f.name"
            class="rounded bg-surface-gray-3 px-2 py-0.5 text-sm text-ink-gray-7"
          >
            {{ f.file_name }}
          </span>
        </div>
        <textarea
          ref="askRef"
          v-model="question"
          rows="1"
          :aria-label="__('Ask Copilot about this ticket')"
          :placeholder="
            __('Ask Copilot about #{0}, or tell it what to do', ticketId)
          "
          class="block max-h-40 min-h-[44px] w-full resize-none border-0 bg-transparent px-3.5 py-2.5 text-base text-ink-gray-9 placeholder:text-ink-gray-5 focus:outline-none focus:ring-0"
          @input="grow"
          @keydown.enter.exact.prevent="ask()"
          @keydown.esc="askRef?.blur()"
        />
        <div class="flex items-center gap-1 px-1.5 pb-1.5">
          <FileUploader
            v-if="copilot.chat.value"
            :upload-args="{
              doctype: 'HDS Copilot Chat',
              docname: copilot.chat.value,
              private: true,
            }"
            @success="(f) => files.push(f)"
          >
            <template #default="{ openFileSelector, uploading }">
              <Button
                variant="ghost"
                :loading="uploading"
                :label="__('Attach a screenshot or a file')"
                @click="openFileSelector()"
              >
                <template #icon>
                  <LucidePaperclip class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </template>
          </FileUploader>
          <div
            v-if="!question.trim() && !files.length"
            class="flex min-w-0 flex-1 gap-1.5 overflow-x-auto hide-scrollbar"
            role="group"
            :aria-label="__('Quick questions')"
          >
            <button
              v-for="q in QUICK"
              :key="q"
              type="button"
              class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base px-3 text-sm text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :disabled="copilot.busy.value"
              @click="ask(q)"
            >
              <LucideSparkles class="size-3.5" aria-hidden="true" />
              {{ q }}
            </button>
          </div>
          <p
            v-else
            class="min-w-0 flex-1 truncate px-1 text-xs text-ink-gray-5"
          >
            {{ __("Enter to send · Shift + Enter for a new line") }}
          </p>
          <Button
            type="submit"
            variant="solid"
            :loading="copilot.busy.value"
            :disabled="!question.trim() && !files.length"
            :label="__('Ask')"
          >
            <template #prefix>
              <LucideArrowUp class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import CommentTextEditor from "@/components/CommentTextEditor.vue";
import EmailEditor from "@/components/EmailEditor.vue";
import type { ReplyTarget } from "@/components/emailReply";
import TypingIndicator from "@/components/TypingIndicator.vue";
import { useDevice } from "@/composables";
import { useScreenSize } from "@/composables/screen";
import { useShortcut } from "@/composables/shortcuts";
import {
  composerMode,
  copilotFocus,
  insertIntoReply,
  showCommentBox,
  showEmailBox,
  startWriting,
  type ComposerMode,
} from "@/pages/ticket/modalStates";
import { __ } from "@/translation";
import { TicketSymbol } from "@/types";
import { onClickOutside } from "@vueuse/core";
import { Button, createResource, FileUploader } from "frappe-ui";
import { computed, inject, nextTick, ref, watch } from "vue";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideLock from "~icons/lucide/lock";
import LucideMail from "~icons/lucide/mail";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideSparkles from "~icons/lucide/sparkles";
import { firstName } from "./inbox";
import { useCopilotThread } from "./useCopilotThread";

const emit = defineEmits<{ sent: [] }>();

const ticket = inject(TicketSymbol)!;
const doc = computed(() => ticket.value.doc);
const ticketId = computed(() => String(doc.value.name));
const contactFirst = computed(() =>
  firstName(doc.value.contact || doc.value.raised_by)
);
// the ticket page re-mounts this per ticket (TicketAgent keys it)
const copilot = useCopilotThread(ticketId.value);
const { isMac } = useDevice();
const { isMobileView } = useScreenSize();

const rootRef = ref<HTMLElement | null>(null);
const emailEditorRef = ref<any>(null);
const commentEditorRef = ref<any>(null);
const askRef = ref<HTMLTextAreaElement | null>(null);

const modes = computed(() => [
  {
    mode: "reply" as ComposerMode,
    key: "r",
    icon: LucideMail,
    label: __("Reply to {0}", contactFirst.value),
    on: "bg-surface-gray-10 text-ink-base",
  },
  {
    mode: "note" as ComposerMode,
    key: "c",
    icon: LucideLock,
    label: isMobileView.value ? __("Note") : __("Note to team"),
    on: "bg-note text-ink-gray-9 ring-1 ring-inset ring-note-border",
  },
  {
    mode: "copilot" as ComposerMode,
    key: "q",
    icon: LucideSparkles,
    label: __("Ask Copilot"),
    on: "bg-surface-gray-3 text-ink-gray-9",
  },
]);

function choose(mode: ComposerMode) {
  if (composerMode.value === mode && mode !== "copilot") {
    // the mode's pill again: open its editor
    startWriting(mode);
    return;
  }
  composerMode.value = mode;
  showEmailBox.value = false;
  showCommentBox.value = false;
  if (mode === "copilot") copilotFocus.value++;
}

// something else opened the reply or the note (the header, the AI card, Getting started): follow it
watch(showEmailBox, (open) => {
  if (open) composerMode.value = "reply";
});
watch(showCommentBox, (open) => {
  if (open) composerMode.value = "note";
});

// --- the reply -------------------------------------------------------------------------------
function submitEmail() {
  if (emailEditorRef.value?.submitMail()) emit("sent");
}

// the same draft as Details → AI assist (helpdesk.api.ai_suggestion), asked for when a reply is near
const draft = createResource({
  url: "helpdesk.api.ai_suggestion.get_suggestion",
  makeParams: () => ({ ticket: ticketId.value }),
});
const draftDismissed = ref(false);
const draftUsed = ref(false);
const draftReady = computed(
  () =>
    !draftDismissed.value &&
    !draftUsed.value &&
    draft.data?.status === "Ready" &&
    Boolean(draft.data?.reply)
);
watch(
  () => composerMode.value,
  (mode) => {
    if (mode === "reply" && !draft.fetched && !draft.loading) draft.fetch();
  },
  { immediate: true }
);
function useDraft() {
  insertIntoReply(ticketId.value, draft.data.reply);
  draftUsed.value = true;
}

watch(showEmailBox, async (open) => {
  if (!open) return;
  await nextTick();
  emailEditorRef.value?.editor?.commands?.focus("start");
});

/** Reply or Reply all on one email: the editor opens with its recipients and the quote. */
async function replyToEmail(target: ReplyTarget) {
  startWriting("reply");
  await nextTick();
  const list = (v: string | string[] | undefined) =>
    typeof v === "string"
      ? v
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : v ?? [];
  emailEditorRef.value?.addToReply(
    target.content,
    list(target.to),
    list(target.cc),
    list(target.bcc)
  );
}

// --- the note --------------------------------------------------------------------------------
function submitComment() {
  if (commentEditorRef.value?.submitComment()) emit("sent");
}
watch(showCommentBox, async (open) => {
  if (!open) return;
  await nextTick();
  commentEditorRef.value?.editor?.commands?.focus();
});

function afterSend() {
  showEmailBox.value = false;
  showCommentBox.value = false;
  emit("sent");
}

// --- the question to Copilot -------------------------------------------------------------------
const QUICK = [
  __("Summarise this ticket"),
  __("Draft a reply"),
  __("Similar tickets"),
  __("Errors on their site"),
];
const question = ref("");
const files = ref<{ name: string; file_name: string }[]>([]);

function grow() {
  const el = askRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

async function ask(text?: string) {
  const words = (text ?? question.value).trim();
  if ((!words && !files.value.length) || copilot.busy.value) return;
  const names = files.value.map((f) => f.name);
  if (!text) question.value = "";
  files.value = [];
  await nextTick();
  grow();
  await copilot.send(words, names);
}

watch(copilotFocus, async () => {
  await nextTick();
  askRef.value?.focus();
});

// --- keyboard: R reply, C note, Q Copilot (not while typing) ----------------------------------
useShortcut("r", () => startWriting("reply"));
useShortcut("c", () => startWriting("note"));
useShortcut("q", () => startWriting("copilot"));

// a click elsewhere folds an open editor; what was written stays (each editor keeps its draft)
const IGNORED = [
  ".tippy-box",
  ".tippy-content",
  ".PopoverContent",
  '[role="dialog"]',
  '[role="menu"]',
  ".dialog-overlay",
];
onClickOutside(
  rootRef,
  () => {
    showEmailBox.value = false;
    showCommentBox.value = false;
  },
  { ignore: IGNORED }
);

defineExpose({ replyToEmail });
</script>
