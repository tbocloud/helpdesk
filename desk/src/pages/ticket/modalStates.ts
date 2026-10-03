import { ref } from "vue";

export const showAssignmentModal = ref(false);
export const showEmailBox = ref(false);
export const showCommentBox = ref(false);
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

export interface ReplyInsert {
  ticketId: string;
  html: string;
}

// Panels outside the composer (the AI suggested reply card) hand text to the
// ticket's EmailEditor through this; the editor clears it once applied.
export const pendingReplyInsert = ref<ReplyInsert | null>(null);

export function insertIntoReply(ticketId: string, html: string) {
  pendingReplyInsert.value = { ticketId: String(ticketId), html };
  showCommentBox.value = false;
  showEmailBox.value = true;
}
