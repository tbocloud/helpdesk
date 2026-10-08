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

/** The header's Reply: opens the email composer, never closes it. */
export function openReplyBox() {
  showCommentBox.value = false;
  showEmailBox.value = true;
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
