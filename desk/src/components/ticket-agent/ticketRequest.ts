/** The customer's request that opens a ticket's chat (Phase 12): who, when, their words. */
export type TicketRequest = {
  who: string;
  customer: string;
  at: string;
  subject: string;
  text: string;
};

export function ticketRequest(
  doc: Record<string, any> | undefined
): TicketRequest | null {
  if (!doc) return null;
  // paragraphs, list items and line breaks stay lines
  const html = (doc.description || "").replace(
    /<br\s*\/?>|<\/(p|div|li|h[1-6]|tr)>/gi,
    "$&\n"
  );
  const text = new DOMParser()
    .parseFromString(html, "text/html")
    .body.textContent?.replace(/\n{3,}/g, "\n\n")
    .trim();
  return {
    who: doc.contact || doc.raised_by || "",
    customer: doc.customer || "",
    at: doc.opening_date
      ? `${doc.opening_date} ${doc.opening_time || ""}`.trim()
      : doc.creation,
    subject: doc.subject || "",
    text: text || "",
  };
}
