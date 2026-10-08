<template>
  <div class="comm-area">
    <div
      class="flex justify-between gap-3 border-t border-outline-gray-2 bg-surface-gray-1 px-6 py-3 md:px-5 md:py-2"
    >
      <div class="flex items-center gap-2">
        <div
          class="flex items-center gap-0.5 rounded-lg bg-surface-gray-2 p-0.5"
          role="group"
          :aria-label="__('Compose')"
        >
          <button
            v-for="mode in modes"
            :key="mode.key"
            type="button"
            class="flex h-11 min-w-11 items-center gap-1.5 rounded-md px-3 md:h-7 md:min-w-0 md:px-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :class="
              mode.active
                ? 'bg-surface-base text-ink-gray-9 shadow-sm'
                : 'text-ink-gray-6 hover:text-ink-gray-9'
            "
            :aria-pressed="mode.active"
            :aria-keyshortcuts="mode.shortcut"
            @click="mode.toggle()"
          >
            <component :is="mode.icon" class="size-4" aria-hidden="true" />
            {{ mode.label }}
            <kbd
              v-if="!isMobileView"
              class="rounded border border-outline-gray-2 px-1 font-mono text-2xs text-ink-gray-5"
              aria-hidden="true"
              >{{ mode.shortcut.toUpperCase() }}</kbd
            >
          </button>
        </div>
        <TypingIndicator :ticketId="ticketId" />
      </div>
      <p
        v-if="showEmailBox && recipientSummary"
        class="min-w-0 self-center truncate text-xs text-ink-gray-5"
        :title="recipientSummary"
      >
        {{ __("To") }}: {{ recipientSummary }}
      </p>
      <p
        v-else-if="showCommentBox"
        class="flex min-w-0 items-center gap-1.5 self-center truncate text-xs text-ink-gray-6"
      >
        <LucideEyeOff class="size-3.5 shrink-0" aria-hidden="true" />
        {{ __("Only agents see comments") }}
      </p>
    </div>
    <Transition name="slide">
      <div
        v-show="showEmailBox"
        ref="emailBoxRef"
        @keydown.ctrl.enter.capture.stop="submitEmail"
        @keydown.meta.enter.capture.stop="submitEmail"
        @keydown.esc.capture.stop="showEmailBox = false"
      >
        <div class="overflow-hidden">
          <EmailEditor
            ref="emailEditorRef"
            :label="
              isMobileView ? 'Send' : isMac ? 'Send (⌘ + ⏎)' : 'Send (Ctrl + ⏎)'
            "
            placeholder="Hi John, we are looking into this issue."
            :ticketId="ticketId"
            :to-emails="toEmails"
            :cc-emails="ccEmails"
            :bcc-emails="bccEmails"
            @submit="
              () => {
                showEmailBox = false;
                emit('update');
              }
            "
            @discard="
              () => {
                showEmailBox = false;
              }
            "
          />
        </div>
      </div>
    </Transition>
    <Transition name="slide">
      <div
        v-show="showCommentBox"
        ref="commentBoxRef"
        @keydown.ctrl.enter.capture.stop="submitComment"
        @keydown.meta.enter.capture.stop="submitComment"
        @keydown.esc.capture.stop="showCommentBox = false"
      >
        <div class="overflow-hidden bg-note">
          <CommentTextEditor
            ref="commentTextEditorRef"
            :label="
              isMobileView
                ? 'Comment'
                : isMac
                ? 'Comment (⌘ + ⏎)'
                : 'Comment (Ctrl + ⏎)'
            "
            :ticketId="ticketId"
            :editable="showCommentBox"
            :doctype="doctype"
            placeholder="@John could you please look into this?"
            @submit="
              () => {
                showCommentBox = false;
                emit('update');
              }
            "
            @discard="
              () => {
                showCommentBox = false;
              }
            "
          />
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { CommentTextEditor, EmailEditor, TypingIndicator } from "@/components";
import { CommentIcon, EmailIcon } from "@/components/icons/";
import { useDevice } from "@/composables";
import { useScreenSize } from "@/composables/screen";
import { useShortcut } from "@/composables/shortcuts";
import { showCommentBox, showEmailBox } from "@/pages/ticket/modalStates";
import { onClickOutside } from "@vueuse/core";
import { computed, ref, watch } from "vue";
import LucideEyeOff from "~icons/lucide/eye-off";

const emit = defineEmits(["update"]);
const content = defineModel("content");
const { isMac } = useDevice();
const { isMobileView } = useScreenSize();
let doc = defineModel();
// let doc = inject(TicketSymbol)?.value.doc
const emailEditorRef = ref(null);
const commentTextEditorRef = ref(null);
const emailBoxRef = ref(null);
const commentBoxRef = ref(null);

function toggleEmailBox() {
  if (showCommentBox.value) {
    showCommentBox.value = false;
  }
  showEmailBox.value = !showEmailBox.value;
}

function toggleCommentBox() {
  if (showEmailBox.value) {
    showEmailBox.value = false;
  }
  showCommentBox.value = !showCommentBox.value;
}

// Reply goes to the customer; a comment is an internal note (styled as one)
const modes = computed(() => [
  {
    key: "reply",
    label: __("Reply"),
    icon: EmailIcon,
    shortcut: "r",
    active: showEmailBox.value,
    toggle: toggleEmailBox,
  },
  {
    key: "comment",
    label: __("Comment"),
    icon: CommentIcon,
    shortcut: "c",
    active: showCommentBox.value,
    toggle: toggleCommentBox,
  },
]);

function submitEmail() {
  if (emailEditorRef.value.submitMail()) {
    emit("update");
  }
}

function submitComment() {
  if (commentTextEditorRef.value.submitComment()) {
    emit("update");
  }
}

function splitIfString(str: string | string[]) {
  if (typeof str === "string") {
    return str.split(",");
  }
  return str;
}

function replyToEmail(data: object) {
  showEmailBox.value = true;

  emailEditorRef.value.addToReply(
    data.content,
    splitIfString(data.to),
    splitIfString(data.cc),
    splitIfString(data.bcc)
  );
}

const props = defineProps({
  doctype: {
    type: String,
    default: "HD Ticket",
  },
  ticketId: {
    type: String,
    default: null,
  },
  toEmails: {
    type: Array,
    default: () => [],
  },
  ccEmails: {
    type: Array,
    default: () => [],
  },
  bccEmails: {
    type: Array,
    default: () => [],
  },
});

// Follows the editor's own recipient list, which changes when replying to a specific email
const recipientSummary = computed(() => {
  const emails = (emailEditorRef.value?.toEmails ?? props.toEmails) as string[];
  return emails.filter(Boolean).join(", ");
});

watch(
  () => showEmailBox.value,
  (value) => {
    if (value) {
      emailEditorRef.value?.editor?.commands?.focus("start");
    }
  }
);

watch(
  () => showCommentBox.value,
  (value) => {
    if (value) {
      commentTextEditorRef.value?.editor?.commands?.focus();
    }
  }
);

useShortcut("r", () => {
  toggleEmailBox();
});
useShortcut("c", () => {
  toggleCommentBox();
});

defineExpose({
  replyToEmail,
  toggleEmailBox,
  toggleCommentBox,
  editor: emailEditorRef,
});

const IGNORED_SELECTORS = [
  ".tippy-box",
  ".tippy-content",
  ".PopoverContent",
  '[role="dialog"]',
  '[role="menu"]',
  ".dialog-overlay",
];

onClickOutside(
  emailBoxRef,
  () => {
    if (showEmailBox.value) {
      showEmailBox.value = false;
    }
  },
  {
    ignore: IGNORED_SELECTORS,
  }
);

onClickOutside(
  commentBoxRef,
  () => {
    if (showCommentBox.value) {
      showCommentBox.value = false;
    }
  },
  {
    ignore: IGNORED_SELECTORS,
  }
);
</script>

<style>
@media screen and (max-width: 640px) {
  .comm-area {
    width: 100vw;
  }
}

.slide-enter-active,
.slide-leave-active {
  display: grid;
  transition: grid-template-rows 0.25s ease;
}
.slide-enter-from,
.slide-leave-to {
  grid-template-rows: 0fr;
}
.slide-enter-to,
.slide-leave-from {
  grid-template-rows: 1fr;
}
</style>
