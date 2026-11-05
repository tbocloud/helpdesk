import type {
  CopilotAction,
  CopilotCardData,
} from "@/components/copilot/CopilotCard.vue";
import { globalStore } from "@/stores/globalStore";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { createResource, toast } from "frappe-ui";
import { computed, ref } from "vue";

/**
 * A ticket's Copilot chat (helpdesk.api.copilot_thread), shared by the ticket's summary (where Copilot stands, its
 * buttons) and its conversation (Copilot's messages and cards). One per ticket, kept while the agent moves between
 * tickets; another person's message, Copilot's next step or a decision in Teams reloads it (realtime).
 */

export type ThreadMessage = {
  name: string;
  direction: "In" | "Out";
  author: string;
  user?: string;
  via: string;
  text: string;
  card: CopilotCardData | null;
  status: string | null;
  at: string;
};

export type CopilotNow = {
  state: string;
  line: string;
  actions: CopilotAction[];
  more: CopilotAction[];
  links: [string, string][];
  muted: boolean;
  categories?: string[];
  /** false: this person reads the chat but may not write in it (Phase 12) */
  can_write?: boolean;
};

export type CopilotPerson = {
  user: string;
  name: string;
  role: "developer" | "coordinator";
};

const API = "helpdesk.api.copilot_thread";

// buttons anyone who may read the ticket may press (helpdesk.copilot.thread.OPEN_VERBS)
const OPEN_VERBS = new Set([
  "approve",
  "reject",
  "snooze",
  "show_fix",
  "release_approve",
  "release_now",
  "release_reject",
  "mute",
  "unmute",
]);

/** Copilot is at work in these run states (the summary's spinning icon). */
export const COPILOT_WORKING = new Set([
  "Queued",
  "Investigating",
  "Preparing Fix",
  "Approved",
  "Merging",
  "Deploying",
  "Verifying",
  "Applying",
]);

function make(ticket: string) {
  const thread = createResource({
    url: `${API}.history`,
    params: { ticket },
    auto: true,
  });
  const messages = computed(
    () => (thread.data?.messages as ThreadMessage[] | undefined) || []
  );
  const now = computed(() => thread.data?.now as CopilotNow | undefined);
  const people = computed(
    () => (thread.data?.people as CopilotPerson[] | undefined) || []
  );
  const chat = computed(() => thread.data?.chat as string | undefined);
  // a decision waits for a person (approve, reject, let Copilot fix it, build, deploy), not Start Copilot
  const needsYou = computed(() =>
    (now.value?.actions ?? []).some((a) => a.verb !== "start")
  );
  const canWrite = computed(() => now.value?.can_write !== false);
  const busy = ref(false);

  async function post(method: string, params: Record<string, unknown>) {
    busy.value = true;
    try {
      return await createResource({ url: `${API}.${method}` }).submit({
        ticket,
        ...params,
      });
    } catch (error) {
      toast.error(errorText(error) || __("Copilot could not do that"));
    } finally {
      busy.value = false;
      thread.reload();
    }
  }

  function send(text: string, files: string[] = []) {
    return post("send", { text, files: JSON.stringify(files) });
  }

  function press(
    action: CopilotAction,
    inputs: Record<string, string> = {},
    message?: string
  ) {
    return post("press", {
      verb: action.verb,
      data: JSON.stringify({ ...action.data, ...(message ? { message } : {}) }),
      inputs: JSON.stringify(inputs),
    });
  }

  /** A card's buttons for this person: someone who may only read keeps the open ones. */
  function forThisPerson(card: CopilotCardData): CopilotCardData {
    if (canWrite.value || !card.actions?.length) return card;
    return {
      ...card,
      actions: card.actions.filter((a) => OPEN_VERBS.has(a.verb)),
    };
  }

  return {
    thread,
    messages,
    now,
    people,
    chat,
    needsYou,
    canWrite,
    busy,
    send,
    press,
    forThisPerson,
  };
}

export type CopilotThread = ReturnType<typeof make>;

const threads: Record<string, CopilotThread> = {};
let listening = false;

function listen() {
  if (listening) return;
  listening = true;
  const { $socket } = globalStore();
  const reload = (data: { ticket?: string | number }) => {
    threads[String(data?.ticket)]?.thread.reload();
  };
  $socket.on("helpdesk:copilot-thread", reload);
  $socket.on("helpdesk:copilot-run", reload);
}

export function useCopilotThread(ticket: string | number): CopilotThread {
  listen();
  const key = String(ticket);
  return (threads[key] ??= make(key));
}
