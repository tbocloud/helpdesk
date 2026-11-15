// The call box: what the person sees between tapping Call and recording how it went
// (docs/leads.md). The hub asks the ERP site where the call is (get_call_status) every few
// seconds, only while the box is open; the call itself is on the person's phone.
import { prepareRing, startRing, stopRing } from "@/composables/ringTone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { call } from "frappe-ui";
import { computed, reactive, watch } from "vue";
import { isUsable, type LeadNumber } from "./leads";
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
  /** the lead's numbers, when the caller has them (else the box asks when they are needed) */
  numbers?: LeadNumber[];
}

export type CallPhase =
  | "placing"
  | "calling"
  | "ringing"
  | "ringing_lead"
  | "on_call"
  | "ended"
  | "timeout"
  /** the person stopped waiting: their phone never rang, or they dialled by mistake */
  | "stopped"
  | "refused";

interface CallStatus {
  state: "calling" | "ringing" | "ringing_lead" | "on_call" | "ended";
  answered?: boolean | null;
  duration?: number | null;
  talk_seconds?: number | null;
  number?: string | null;
  call?: string | null;
  /** saved, pending (still being downloaded) or none; absent from an older TBO Smart */
  recording_state?: "saved" | "pending" | "none" | null;
}

const POLL_MS = 2500;
const MAX_POLL_MS = 15_000;
/** no sign of the call after this long: stop asking and let the person record the result */
const LOST_AFTER_MS = 180_000;
const MAX_CALL_MS = 60 * 60_000;
/** without live updates the box still offers "Record the result" after this long */
export const RECORD_AFTER_MS = 45_000;
/** after the report, the recording takes a moment: ask again this often, this many times */
const RECORDING_POLL_MS = 4000;
const RECORDING_POLLS = 8;

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
  /** the finished call's name (to open it on the lead) and whether its recording is saved */
  callName: "",
  recording: "" as "" | "saved" | "pending" | "none",
  numbers: undefined as LeadNumber[] | undefined,
});

let timer: ReturnType<typeof setTimeout> | undefined;
let failures = 0;
let session = 0;

const WAITING: CallPhase[] = ["placing", "calling", "ringing", "ringing_lead"];
export const isWaiting = (phase: CallPhase) => WAITING.includes(phase);
const isOver = (phase: CallPhase) =>
  phase === "ended" || phase === "timeout" || phase === "stopped";

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

/** The lead's other usable numbers, for "Try another number" (the dialled one left out). */
export const otherNumbers = computed(() => {
  const dialled = digits(box.number);
  return (box.numbers ?? []).filter(
    (n) => isUsable(n) && !!dialled && digits(n.number) !== dialled
  );
});

/** Where "Try another number" is offered: the call didn't connect. */
export const canTryAnother = computed(
  () =>
    otherNumbers.value.length > 0 &&
    (box.phase === "refused" ||
      box.phase === "timeout" ||
      box.phase === "stopped" ||
      (box.phase === "ended" && box.answered === false))
);

/** The last 10 digits: how a number typed with +91 or a 0 meets the one the ERP site dialled. */
function digits(value?: string | null) {
  return (value || "").replace(/\D/g, "").slice(-10);
}

/** The Call actions' one entry: opens the box and asks the ERP site to ring the person's phone.
 * `another`: the person chose a different number in the box, so a call that didn't connect
 * (still waiting for its result) is replaced. */
export function placeCall(next: BoxCall, another = false) {
  if (box.open && !another && !canClose.value) {
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
    callName: "",
    recording: "",
    numbers: next.numbers,
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
  if (
    (isWaiting(box.phase) && age > LOST_AFTER_MS) ||
    (box.phase === "on_call" && age > MAX_CALL_MS)
  ) {
    box.phase = "timeout";
    findLostCall(mine);
    return;
  }
  schedule(Math.min(POLL_MS * 2 ** failures, MAX_POLL_MS));
}

/** The box lost the call: the ERP site may have missed the provider's report, so it looks
 * in the provider's call list once; a call it finds ends the wait with its real result. */
async function findLostCall(mine: number) {
  try {
    await call("helpdesk.api.leads.refresh_call", {
      reference_id: box.referenceId,
    });
    const status: CallStatus = await call(
      "helpdesk.api.leads.get_call_status",
      { reference_id: box.referenceId }
    );
    if (mine === session && status.state === "ended") apply(status);
  } catch {
    // the person can still record the result by hand
  }
}

function apply(status: CallStatus) {
  if (status.number) box.number = status.number;
  if (status.state === "ended") {
    box.answered = !!status.answered;
    box.seconds = status.talk_seconds || status.duration || 0;
    box.callName = status.call || "";
    box.recording = status.recording_state || "";
    const first = box.phase !== "ended";
    box.phase = "ended";
    if (first) recordResult();
    if (box.answered && box.recording === "pending") watchRecording(session, 0);
    return;
  }
  if (status.state === "on_call" && box.phase !== "on_call")
    box.onCallAt = Date.now();
  // a status never goes back to an earlier one
  if (rank(status.state) >= rank(box.phase)) box.phase = status.state;
}

/** The recording is downloaded after the report: ask a few more times until it is saved. */
function watchRecording(mine: number, tries: number) {
  clearTimeout(timer);
  if (tries >= RECORDING_POLLS) return;
  timer = setTimeout(async () => {
    if (!box.open || mine !== session) return;
    try {
      const status: CallStatus = await call(
        "helpdesk.api.leads.get_call_status",
        { reference_id: box.referenceId }
      );
      if (mine !== session) return;
      box.recording = status.recording_state || "";
      if (box.recording !== "pending") return;
    } catch {
      // a later try, or the lead's own timeline, shows it
    }
    watchRecording(mine, tries + 1);
  }, RECORDING_POLL_MS);
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

/** "Stop waiting": the person never picked up their phone, or dialled by mistake. The box
 * stops asking and ringing, and the result sheet opens (it can also say "Tapped by mistake"). */
export function stopWaiting() {
  if (!isWaiting(box.phase)) return;
  session++;
  clearTimeout(timer);
  box.phase = "stopped";
  recordResult();
}

/** The lead's numbers, read when "Try another number" needs them and the caller had none. */
async function loadNumbers() {
  const lead = box.call?.lead;
  if (!lead || box.numbers) return;
  try {
    const detail = await call("helpdesk.api.leads.get_lead", { name: lead });
    if (box.call?.lead === lead) box.numbers = detail?.lead?.numbers ?? [];
  } catch {
    box.numbers = [];
  }
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

// the numbers are read only when a call didn't connect
watch(
  () => [box.phase, box.answered] as const,
  ([phase, answered]) => {
    if (
      phase === "refused" ||
      phase === "timeout" ||
      phase === "stopped" ||
      (phase === "ended" && answered === false)
    )
      loadNumbers();
  }
);

// the ring goes on while the phones ring, and stops the moment the call is picked, over or refused
watch(
  () => [box.open, box.phase] as const,
  ([open, phase]) => {
    if (open && isWaiting(phase)) startRing("ringback");
    else stopRing("ringback");
  }
);
