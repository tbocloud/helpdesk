import { ref } from "vue";

export const showAssignmentModal = ref(false);
export const showEmailBox = ref(false);
export const showCommentBox = ref(false);
// the ticket's one Create task dialog lives in the Linked work section; the
// header menu and the estimate card open it through this
export const showCreateTask = ref(false);
export function toggleEmailBox() {
  if (showCommentBox.value) {
    showCommentBox.value = false;
  }
  showEmailBox.value = !showEmailBox.value;
}
export function toggleCommentBox() {
  if (showEmailBox.value) {
    showEmailBox.value = false;
  }
  showCommentBox.value = !showCommentBox.value;
}

/** The ticket's one box to write in (Phase 16): a reply to the customer, a note to the team, or a question to
 * Copilot. `showEmailBox` / `showCommentBox` say whether the reply or the note editor is open. */
export type ComposerMode = "reply" | "note" | "copilot";
export const composerMode = ref<ComposerMode>("reply");
// counts up each time something asks for the Copilot box, which then takes the focus
export const copilotFocus = ref(0);

export function startWriting(mode: ComposerMode) {
  composerMode.value = mode;
  showEmailBox.value = mode === "reply";
  showCommentBox.value = mode === "note";
  if (mode === "copilot") copilotFocus.value++;
}

/** The header's and the AI card's Reply: the email editor open, never closed. */
export function openReplyBox() {
  startWriting("reply");
}

export interface ReplyInsert {
  ticketId: string;
  html: string;
}

// Panels outside the composer (the AI suggested reply card) hand text to the
// ticket's EmailEditor through this; the editor clears it once applied.
export const pendingReplyInsert = ref<ReplyInsert | null>(null);

export function insertIntoReply(ticketId: string, html: string) {
  pendingReplyInsert.value = { ticketId: String(ticketId), html };
  openReplyBox();
}
