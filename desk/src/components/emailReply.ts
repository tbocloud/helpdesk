/**
 * Who a reply to one email goes to (the ticket's email cards and the inbox's bubbles share this).
 * Reply: back to the sender, or to the original recipients when the agent sent it.
 * Reply all: the sender in To and everyone else in Cc, without the agent and the sender twice.
 */

export interface EmailForReply {
  content: string;
  sender: { name?: string };
  to?: string | string[];
  cc?: string | string[];
  bcc?: string | string[];
}

export interface ReplyTarget {
  content: string;
  to: string | string[] | undefined;
  cc?: string[];
  bcc?: string[];
}

/** A comma list split outside quotes ("Rahman, Aisha" <a@x> stays one), without the excluded addresses. */
export function normalizeAndFilter(
  field: string | string[] | undefined,
  valuesToExclude: string[] = []
): string[] {
  let arr: string[] = [];
  let current = "";
  let inQuotes = false;
  if (typeof field === "string") {
    for (const char of field) {
      if (char === '"') {
        inQuotes = !inQuotes;
        current += char;
      } else if (char === "," && !inQuotes) {
        arr.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    if (current) arr.push(current.trim());
  } else {
    arr = field || [];
  }
  return arr.filter(Boolean).filter((item) => !valuesToExclude.includes(item));
}

export function replyTo(email: EmailForReply, user: string): ReplyTarget {
  return {
    content: email.content,
    to: user === email.sender.name ? email.to : email.sender.name,
  };
}

export function replyAllTo(email: EmailForReply, user: string): ReplyTarget {
  const sender = email.sender.name || "";
  const exclude = [user, sender];
  const to = normalizeAndFilter(email.to, exclude);
  const cc = normalizeAndFilter(email.cc, exclude);
  const bcc = normalizeAndFilter(email.bcc, exclude);
  // the agent sent it: everyone it went to; otherwise the sender, and the rest in Cc
  return user === sender
    ? { content: email.content, to: to.join(", "), cc, bcc }
    : { content: email.content, to: sender, cc: [...to, ...cc], bcc };
}
