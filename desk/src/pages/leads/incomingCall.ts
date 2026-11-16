// A call coming in to the person's phone while the hub is open: the ERP site knows it from
// CallerDesk's Live Call events. Asked every 10 seconds, only while the tab is visible and only
// for people set up for calling (docs/leads.md).
import { call } from "frappe-ui";
import { ref } from "vue";

export interface IncomingCall {
  call: string;
  number: string | null;
  lead: string | null;
  lead_name: string | null;
  state: "ringing" | "ringing_lead" | "on_call";
}

export const INCOMING_POLL_MS = 10_000;

export const incoming = ref<IncomingCall | null>(null);

const dismissed = new Set<string>();
// the ERP site says when the person isn't set up for calling: then nothing more is asked
let enabled = true;

export async function checkIncoming() {
  if (!enabled) return;
  try {
    const answer: { enabled?: boolean; call?: IncomingCall | null } =
      await call("helpdesk.api.leads.get_incoming_call");
    enabled = answer?.enabled !== false;
    const ringing = answer?.call;
    // once it is picked up there is nothing left to announce
    incoming.value =
      ringing && ringing.state !== "on_call" && !dismissed.has(ringing.call)
        ? ringing
        : null;
  } catch {
    // a missed check only delays the notice
  }
}

export function dismissIncoming() {
  if (incoming.value) dismissed.add(incoming.value.call);
  incoming.value = null;
}
