// The call box: what the person sees between tapping Call and recording how it went
// (docs/leads.md). The hub asks the ERP site where the call is (get_call_status) every few
// seconds, only while the box is open; the call itself is on the person's phone.
import { prepareRing, startRing, stopRing } from "@/composables/ringTone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { call } from "frappe-ui";
import { computed, reactive, watch } from "vue";
import { askFor, askNote, pendingCalls, startCall } from "./pendingCalls";

/** The lead and number a Call action passes, and what the box says about the lead. */
export interface BoxCall {
  lead: string;
  lead_name: string;
  company?: string | null;
  /** the number shown when the ERP site hasn't said which was dialled */
  phone?: string | null;
  /** one of the lead's own numbers (null: the main one) */
  number: string | null;
  /** the call in Today's calls it belongs to */
  item?: string | null;
  product?: string | null;
  intro?: string | null;
}

export type CallPhase =
  | "placing"
  | "calling"
  | "ringing"
  | "ringing_lead"
  | "on_call"
  | "ended"
  | "timeout"
  | "refused";

interface CallStatus {
  state: "calling" | "ringing" | "ringing_lead" | "on_call" | "ended";
  answered?: boolean | null;
  duration?: number | null;
  talk_seconds?: number | null;
  number?: string | null;
}

const POLL_MS = 2500;
const MAX_POLL_MS = 15_000;
/** no sign of the call after this long: stop asking and let the person record the result */
const LOST_AFTER_MS = 180_000;
const MAX_CALL_MS = 60 * 60_000;
/** without live updates the box still offers "Record the result" after this long */
export const RECORD_AFTER_MS = 45_000;

export const box = reactive({
  open: false,
  minimised: false,
  phase: "placing" as CallPhase,
  call: null as BoxCall | null,
  referenceId: "",
  number: "",
  message: "",
  note: "",
  answered: null as boolean | null,
  seconds: 0,
  startedAt: 0,
  onCallAt: 0,
});

let timer: ReturnType<typeof setTimeout> | undefined;
let failures = 0;
let session = 0;

const WAITING: CallPhase[] = ["placing", "calling", "ringing", "ringing_lead"];
export const isWaiting = (phase: CallPhase) => WAITING.includes(phase);
const isOver = (phase: CallPhase) => phase === "ended" || phase === "timeout";

/** The call being placed right now (the Call button that was tapped shows it is working). */
export const placing = computed(() =>
  box.open && box.phase === "placing" ? box.call : null
);

/** The lead's call still waits for its result. */
export const resultPending = computed(
  () => !!box.call && pendingCalls.value.some((c) => c.lead === box.call?.lead)
);

/** A call in progress can't be closed, only minimised; once it is over, only after the result. */
export const canClose = computed(
  () =>
    !box.call ||
    box.phase === "refused" ||
    (isOver(box.phase) && !resultPending.value)
);

/** The Call actions' one entry: opens the box and asks the ERP site to ring the person's phone. */
export function placeCall(next: BoxCall) {
  if (box.open && !canClose.value) {
    box.minimised = false;
    return;
  }
  // from the tap itself, so the browser allows the ring that follows
  prepareRing();
  const mine = ++session;
  Object.assign(box, {
    open: true,
    minimised: false,
    phase: "placing",
    call: next,
    referenceId: "",
    number: next.number || next.phone || "",
    message: "",
    note: "",
    answered: null,
    seconds: 0,
    startedAt: Date.now(),
    onCallAt: 0,
  });
  call("helpdesk.api.leads.click_to_call", {
    name: next.lead,
    number: next.number,
  })
    .then((placed: { number?: string; reference_id?: string }) => {
      if (mine !== session) return;
      box.phase = "calling";
      box.number = placed?.number || box.number;
      box.referenceId = placed?.reference_id || "";
      startCall({
        lead: next.lead,
        lead_name: next.lead_name,
        phone: next.phone || next.number || "",
        number: next.number,
        item: next.item,
        via: "myoperator",
      });
      if (box.referenceId) schedule(0);
    })
    .catch((e: unknown) => {
      if (mine !== session) return;
      box.phase = "refused";
      box.message = errorText(
        e,
        __("Couldn't place the call. Try again in a minute.")
      );
    });
}

function schedule(after: number) {
  clearTimeout(timer);
  timer = setTimeout(poll, after);
}

async function poll() {
  const mine = session;
  if (!box.open || !box.referenceId || mine !== session) return;
  try {
    const status: CallStatus = await call(
      "helpdesk.api.leads.get_call_status",
      { reference_id: box.referenceId }
    );
    if (mine !== session) return;
    failures = 0;
    apply(status);
  } catch {
    if (mine !== session) return;
    failures++;
  }
  if (!box.open || mine !== session || isOver(box.phase)) return;
  const age = Date.now() - box.startedAt;
  if (isWaiting(box.phase) && age > LOST_AFTER_MS) {
    box.phase = "timeout";
    return;
  }
  if (box.phase === "on_call" && age > MAX_CALL_MS) {
    box.phase = "timeout";
    return;
  }
  schedule(Math.min(POLL_MS * 2 ** failures, MAX_POLL_MS));
}

function apply(status: CallStatus) {
  if (status.number) box.number = status.number;
  if (status.state === "ended") {
    box.answered = !!status.answered;
    box.seconds = status.talk_seconds || status.duration || 0;
    box.phase = "ended";
    recordResult();
    return;
  }
  if (status.state === "on_call" && box.phase !== "on_call")
    box.onCallAt = Date.now();
  // a status never goes back to an earlier one
  if (rank(status.state) >= rank(box.phase)) box.phase = status.state;
}

function rank(phase: string) {
  return ["placing", "calling", "ringing", "ringing_lead", "on_call"].indexOf(
    phase
  );
}

/** Opens the "How did it go?" sheet, with what was typed during the call already in it. */
export function recordResult() {
  if (!box.call) return;
  askNote.value = box.note;
  askFor.value = box.call.lead;
}

export function minimise(value = true) {
  box.minimised = value;
}

export function closeBox() {
  if (!canClose.value) return;
  session++;
  clearTimeout(timer);
  box.open = false;
  box.call = null;
}

// the ring goes on while the phones ring, and stops the moment the call is picked, over or refused
watch(
  () => [box.open, box.phase] as const,
  ([open, phase]) => {
    if (open && isWaiting(phase)) startRing("ringback");
    else stopRing("ringback");
  }
);
