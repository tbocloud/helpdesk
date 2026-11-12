// Calls without a result: tapping Call remembers the lead until a result is recorded or the
// call is dismissed with a reason (helpdesk.api.pending_calls, docs/leads.md).
import { __ } from "@/translation";
import { call, createResource } from "frappe-ui";
import { computed, ref } from "vue";

export interface PendingCall {
  lead: string;
  lead_name: string;
  phone: string;
  /** the lead's number that was dialled (null: its main number) */
  number: string | null;
  /** the call in Today's calls it belongs to */
  item: string | null;
  /** the phone's own dialler, or MyOperator ringing the person's phone */
  via: "phone" | "myoperator";
  at: string;
}

interface PendingAnswer {
  count: number;
  calls: PendingCall[];
}

/** Why a call can be taken off without a result. */
export const DISMISS_REASONS = [
  { value: "Didn't call", label: __("I didn't call") },
  { value: "Tapped by mistake", label: __("Tapped by mistake") },
];

/** MyOperator rings the person's phone; the page stays open, so the sheet comes up on its own
 * after this long, when the call is likely over. */
const MYOPERATOR_ASK_AFTER_MS = 45_000;

const list = createResource({
  url: "helpdesk.api.pending_calls.get_pending_calls",
});

/** The person's calls without a result, oldest first. */
export const pendingCalls = computed<PendingCall[]>(
  () => (list.data as PendingAnswer | undefined)?.calls ?? []
);

/** The lead whose result sheet should open now (set when the person comes back from a call). */
export const askFor = ref("");
/** Bumped when a call of Today's calls is answered from the call result sheet: the queue
 * reads again at once, so the call can't be answered twice from its row. */
export const queueChanged = ref(0);
// a call placed from the phone's dialler: the page loses focus, and the sheet opens on return
let awaitingReturn = "";
let timer: ReturnType<typeof setTimeout> | undefined;

export function loadPendingCalls() {
  return list.reload();
}

export function setPendingCalls(answer: PendingAnswer) {
  list.setData(answer);
}

/** Remembers a call the person just placed, and arranges for the result sheet to follow. */
export function startCall(placed: {
  lead: string;
  lead_name?: string;
  phone?: string;
  number?: string | null;
  item?: string | null;
  via: "phone" | "myoperator";
}) {
  call("helpdesk.api.pending_calls.start_call", {
    ...placed,
    lead_name: placed.lead_name || null,
    phone: placed.phone || null,
    number: placed.number || null,
    item: placed.item || null,
  })
    .then((answer: PendingAnswer) => setPendingCalls(answer))
    // a reminder only: a failure must never stop the call
    .catch(() => {});
  if (placed.via === "phone") {
    awaitingReturn = placed.lead;
  } else {
    clearTimeout(timer);
    timer = setTimeout(() => {
      askFor.value = placed.lead;
    }, MYOPERATOR_ASK_AFTER_MS);
  }
}

/** The person is back on the page: ask about the call they left to make. */
export function cameBack() {
  loadPendingCalls();
  if (!awaitingReturn) return;
  askFor.value = awaitingReturn;
  awaitingReturn = "";
}

export function dismissCall(lead: string, reason: string) {
  return call("helpdesk.api.pending_calls.dismiss_pending_call", {
    lead,
    reason,
  }).then((answer: PendingAnswer) => setPendingCalls(answer));
}

/** The call back times the sheet offers, as the ERP site takes them. */
export function callBackIn(hours: number) {
  return erpTime(new Date(Date.now() + hours * 3_600_000));
}

export function callBackTomorrow() {
  const day = new Date();
  day.setDate(day.getDate() + 1);
  day.setHours(10, 0, 0, 0);
  return erpTime(day);
}

function erpTime(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}
