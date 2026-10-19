import { createResource, toast } from "frappe-ui";
import { defineStore } from "pinia";
import { ref } from "vue";
import { globalStore } from "./globalStore";

export interface CopilotCard {
  title: string;
  lines: string[];
  facts: [string, string][];
  links: [string, string][];
  actions: {
    label: string;
    verb: string;
    style: string;
    data: Record<string, unknown>;
  }[];
  inputs: { id: string; label: string; multiline?: boolean }[];
  tone: string;
}

export interface CopilotMessage {
  name: string;
  direction: "In" | "Out";
  text: string;
  card: CopilotCard | null;
  status: string | null;
  at: string;
}

/** The Copilot panel: the staff assistant's chat on the web (helpdesk.api.copilot_chat). */
export const useCopilotChatStore = defineStore("copilotChat", () => {
  const { $socket } = globalStore();
  const visible = ref(false);
  const chat = ref("");
  const messages = ref<CopilotMessage[]>([]);
  const busy = ref(false);

  function apply(data: { chat: string; messages: CopilotMessage[] }) {
    chat.value = data.chat;
    messages.value = data.messages;
  }

  const history = createResource({
    url: "helpdesk.api.copilot_chat.history",
    onSuccess: apply,
  });

  async function call(url: string, params: Record<string, unknown>) {
    busy.value = true;
    try {
      const data = await createResource({ url }).submit(params);
      apply(data);
    } catch (error: any) {
      toast.error(error?.messages?.[0] || "TBO Copilot could not answer");
    } finally {
      busy.value = false;
    }
  }

  function send(message: string, files: string[]) {
    return call("helpdesk.api.copilot_chat.send", {
      message,
      files: JSON.stringify(files),
    });
  }

  function press(
    cardMessage: string,
    verb: string,
    data: Record<string, unknown>,
    inputs: Record<string, string>
  ) {
    return call("helpdesk.api.copilot_chat.press", {
      verb,
      data: JSON.stringify(data),
      inputs: JSON.stringify(inputs),
      card_message: cardMessage,
    });
  }

  function toggle() {
    visible.value = !visible.value;
    if (visible.value) history.reload();
  }

  // a card sent from the hub (a fix to approve, news, the digest) shows at once
  $socket.on("helpdesk:copilot-chat", () => {
    if (visible.value) history.reload();
  });

  return { visible, chat, messages, busy, toggle, send, press, history };
});
