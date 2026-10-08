import type {
  FeedbackActivity,
  Resource,
  TicketActivities,
  TicketActivity,
  TicketTab,
} from "@/types";
import { computed, type Ref } from "vue";

const VIEWED = "viewed this";

/**
 * The ticket's timeline for the agent pages (desktop and phone): emails,
 * comments, calls and history in time order, consecutive history by the same
 * person folded together, and the customer's feedback last.
 */
export function useTicketActivities(
  activities: Ref<Resource<TicketActivities> | undefined>,
  ticketDoc: Ref<Record<string, any> | undefined>
) {
  const all = computed<TicketActivity[]>(() => {
    const data = activities.value?.data;
    if (!data) return [];

    const emails = data.communications.map((email: any, idx: number) => ({
      subject: email.subject,
      content: email.content,
      sender: { name: email.user.email, full_name: email.user.name },
      to: email.recipients,
      type: "email",
      key: email.creation,
      cc: email.cc,
      bcc: email.bcc,
      creation: email.communication_date || email.creation,
      attachments: email.attachments,
      name: email.name,
      deliveryStatus: email.delivery_status,
      // Sent: an agent's reply; Received: from the customer
      direction: email.sent_or_received,
      aiDrafted: !!email.custom_ai_drafted,
      isFirstEmail: idx === 0,
    }));

    const comments = data.comments.map((comment: any) => ({
      name: comment.name,
      type: "comment",
      key: comment.creation,
      commentedBy: comment.commented_by,
      commenter: comment.user.name,
      creation: comment.creation,
      content: comment.content,
      attachments: comment.attachments,
    }));

    const history = [...data.history, ...data.views].map((h: any) => {
      let action = h.action;
      if (action && h.owner && action.includes(h.owner)) {
        action = action.replace(h.owner, "themselves");
      }
      return {
        type: "history",
        key: h.creation,
        content: action || VIEWED,
        creation: h.creation,
        user: h.user.name + " ",
      };
    });

    const calls = (data as any).calls.map((call: any) => ({
      ...call,
      type: "call",
      name: call.name,
      key: call.creation,
      call_type: call.type,
      content: `${call.caller || "Unknown"} made a call to ${
        call.receiver || "Unknown"
      }`,
      duration: call.duration ? call.duration + "s" : "0s",
    }));

    const sorted: any[] = [...emails, ...comments, ...history, ...calls].sort(
      (a, b) => new Date(a.creation).getTime() - new Date(b.creation).getTime()
    );

    const result: any[] = [];
    let i = 0;
    while (i < sorted.length) {
      const current = sorted[i];
      if (current.type === "history") {
        current.relatedActivities = [current];
        for (let j = i + 1; j < sorted.length + 1; j++) {
          const next = sorted[j];
          if (
            next &&
            next.user === current.user &&
            next.content !== VIEWED &&
            !next.content.includes("assigned") &&
            !next.content.includes("unassigned")
          ) {
            current.relatedActivities.push(next);
          } else {
            result.push(current);
            i = j - 1;
            break;
          }
        }
      } else {
        result.push(current);
      }
      i++;
    }

    const doc = ticketDoc.value;
    if (doc?.feedback_rating === 0) return result;
    const feedback: FeedbackActivity = {
      type: "feedback",
      key: "feedback-activity",
      feedback_rating: doc?.feedback_rating,
      feedback_extra: doc?.feedback_extra,
      feedback: doc?.feedback,
      sender: { name: doc?.raised_by, full_name: doc?.contact },
    };
    result.push(feedback);
    return result;
  });

  function filterActivities(tab: TicketTab): TicketActivity[] {
    if (tab === "activity") return all.value;
    return all.value.filter((activity) => activity.type === tab);
  }

  return { activities: all, filterActivities };
}
