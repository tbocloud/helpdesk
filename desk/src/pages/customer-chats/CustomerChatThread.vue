<template>
  <div class="flex h-full min-h-0">
    <div class="flex min-w-0 flex-1 flex-col">
      <!-- header -->
      <div
        class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2.5"
      >
        <Button
          class="md:hidden"
          variant="ghost"
          :label="__('Back')"
          icon-left="lucide-arrow-left"
          @click="emit('back')"
        />
        <div v-if="chat" class="min-w-0 flex-1">
          <div class="truncate text-lg font-semibold text-ink-gray-9">
            {{ chat.user }} · {{ chat.customer }}
          </div>
          <div class="flex flex-wrap items-center gap-1">
            <Badge :label="chat.state" theme="gray" size="sm" />
            <Badge
              v-if="chat.asked_for_person && chat.state !== 'Closed'"
              :label="__('Asked for a person')"
              theme="orange"
              size="sm"
            />
          </div>
        </div>
        <div v-if="chat" class="flex flex-wrap gap-2">
          <Button
            v-if="data?.can_take_over"
            :label="__('I\'ll answer')"
            :loading="busy"
            @click="takeOver"
          />
          <Button
            v-if="chat.ticket"
            variant="ghost"
            :label="__('Ticket #{0}', chat.ticket)"
            @click="openTicket(chat.ticket)"
          />
        </div>
      </div>

      <div
        v-if="notice"
        class="mx-4 mt-2 rounded-lg px-3 py-2 text-p-sm"
        :class="
          notice.ok
            ? 'bg-surface-green-1 text-ink-green-4'
            : 'bg-surface-red-1 text-ink-red-4'
        "
      >
        {{ notice.text }}
      </div>

      <!-- messages -->
      <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <div v-if="!data && loading" class="text-p-sm text-ink-gray-5">
          {{ __("Loading…") }}
        </div>
        <div
          v-for="m in messages"
          :key="m.name"
          class="mb-2 flex"
          :class="placeOf(m)"
        >
          <!-- Copilot's stages and the system's lines -->
          <div
            v-if="m.from === 'System'"
            class="max-w-[80%] text-center text-xs text-ink-gray-5"
          >
            {{ m.card?.title ? m.card.title + ": " : "" }}{{ m.text }} ·
            {{ timeOf(m.at) }}
          </div>
          <div
            v-else
            class="max-w-[80%] rounded-xl px-3 py-2"
            :class="bubbleOf(m)"
          >
            <div class="mb-0.5 text-xs text-ink-gray-5">
              {{ whoOf(m) }} · {{ timeOf(m.at) }}
              <span v-if="m.from !== 'Customer' && !m.delivered">
                · {{ __("not delivered yet") }}</span
              >
            </div>
            <div
              v-if="m.text"
              class="whitespace-pre-wrap break-words text-p-base text-ink-gray-9"
            >
              {{ m.text }}
            </div>
            <!-- a card, read-only: what the customer saw -->
            <div
              v-if="m.card && (m.card.facts?.length || m.card.actions?.length)"
              class="mt-1 rounded-lg border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-p-sm"
            >
              <div
                v-for="(f, i) in m.card.facts || []"
                :key="i"
                class="text-ink-gray-7"
              >
                <span class="text-ink-gray-5">{{ f[0] }}:</span> {{ f[1] }}
              </div>
              <div
                v-if="m.card.actions?.length"
                class="mt-1 flex flex-wrap gap-1"
              >
                <span
                  v-for="(a, i) in m.card.actions"
                  :key="i"
                  class="rounded border border-outline-gray-2 px-2 py-0.5 text-xs text-ink-gray-6"
                  :title="__('The customer saw this button')"
                  >{{ a.label }}</span
                >
              </div>
            </div>
            <div
              v-for="(f, i) in m.files"
              :key="i"
              class="mt-1 text-p-sm text-ink-gray-6"
            >
              📎 {{ f.name }}
            </div>
          </div>
        </div>
      </div>

      <!-- reply box -->
      <div class="border-t border-outline-gray-2 px-4 py-3">
        <textarea
          v-model="draft"
          rows="3"
          class="w-full resize-y rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-p-base text-ink-gray-9 focus:border-outline-gray-4 focus:outline-none"
          :placeholder="
            __('Reply in the customer\'s ERP chat (Ctrl+Enter sends)')
          "
          :disabled="sending || chat?.state === 'Closed'"
          @keydown.enter.ctrl.prevent="send"
          @keydown.enter.meta.prevent="send"
        />
        <div class="mt-2 flex items-center gap-3">
          <span class="text-p-sm text-ink-gray-5">
            {{
              data?.can_take_over
                ? __(
                    "Sending takes the chat over from the AI. Files: attach them on the ticket for now."
                  )
                : __("Files: attach them on the ticket for now.")
            }}
          </span>
          <Button
            class="ml-auto"
            variant="solid"
            :label="__('Send')"
            :loading="sending"
            :disabled="!draft.trim() || chat?.state === 'Closed'"
            @click="send"
          />
        </div>
      </div>
    </div>

    <!-- what the AI gathered, where the user was, the ticket -->
    <aside
      v-if="data"
      class="hidden w-72 shrink-0 overflow-y-auto border-l border-outline-gray-2 px-4 py-3 lg:block"
      :aria-label="__('About this chat')"
    >
      <div class="mb-4">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("Customer") }}
        </div>
        <div class="text-base text-ink-gray-9">{{ chat?.customer }}</div>
        <div v-if="chat?.site" class="text-p-sm text-ink-gray-7">
          {{ chat.site }}
        </div>
        <div class="text-p-sm text-ink-gray-7">{{ chat?.user }}</div>
        <div v-if="data.context.roles.length" class="text-xs text-ink-gray-6">
          {{ data.context.roles.join(", ") }}
        </div>
      </div>
      <div
        v-if="data.context.doctype || data.context.page || data.context.error"
        class="mb-4"
      >
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("Where they were") }}
        </div>
        <div v-if="data.context.doctype" class="text-p-sm text-ink-gray-8">
          {{ data.context.doctype }} {{ data.context.docname }}
        </div>
        <div v-else-if="data.context.page" class="text-p-sm text-ink-gray-8">
          {{ data.context.page }}
        </div>
        <div
          v-if="data.context.error"
          class="mt-1 rounded bg-surface-red-1 px-2 py-1 text-xs text-ink-gray-8"
        >
          {{ data.context.error }}
        </div>
      </div>
      <div v-if="data.gathered.length" class="mb-4">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("What the AI gathered") }}
        </div>
        <div v-for="g in data.gathered" :key="g.label" class="mb-1">
          <div class="text-xs text-ink-gray-5">{{ g.label }}</div>
          <div class="whitespace-pre-wrap text-p-sm text-ink-gray-8">
            {{ g.value }}
          </div>
        </div>
      </div>
      <div v-if="data.ticket" class="mb-4">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("Ticket") }}
        </div>
        <button
          type="button"
          class="text-left text-base text-ink-blue-3 underline"
          @click="openTicket(data.ticket.name)"
        >
          #{{ data.ticket.name }} {{ data.ticket.subject }}
        </button>
        <div class="text-p-sm text-ink-gray-7">
          {{ data.ticket.status }} · {{ data.ticket.priority }}
        </div>
        <div class="text-p-sm text-ink-gray-7">
          {{ __("With") }}:
          {{
            data.ticket.assignees.map((a) => a.name).join(", ") ||
            __("nobody yet")
          }}
        </div>
      </div>
      <div v-if="data.open_tickets.length">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("The customer's open tickets") }}
        </div>
        <button
          v-for="t in data.open_tickets"
          :key="t.name"
          type="button"
          class="block text-left text-p-sm text-ink-blue-3 underline"
          @click="openTicket(t.name)"
        >
          #{{ t.name }} {{ t.subject }} ({{ t.status }})
        </button>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { globalStore } from "@/stores/globalStore";
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import { Badge, Button, call } from "frappe-ui";
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

const API = "helpdesk.api.customer_chats";
const REFRESH_MS = 60000;

type Card = {
  title?: string;
  lines?: string[];
  facts?: [string, string][];
  actions?: { label: string }[];
};
type Message = {
  name: string;
  from: "Customer" | "Assistant" | "Agent" | "System";
  kind: string;
  text: string;
  card: Card | null;
  files: { name: string }[];
  delivered: boolean;
  at: string;
};
type Data = {
  chat: {
    name: string;
    customer: string;
    site: string;
    user: string;
    state: string;
    asked_for_person: boolean;
    ticket: string;
  };
  context: {
    page: string;
    doctype: string;
    docname: string;
    roles: string[];
    error: string;
  };
  gathered: { label: string; value: string }[];
  ticket: {
    name: string;
    subject: string;
    status: string;
    priority: string;
    assignees: { name: string }[];
  } | null;
  open_tickets: { name: string; subject: string; status: string }[];
  messages: Message[];
  can_take_over: boolean;
};

const props = defineProps<{ name: string }>();
const emit = defineEmits<{ (e: "back"): void; (e: "changed"): void }>();
const router = useRouter();

const data = ref<Data | null>(null);
const loading = ref(false);
const sending = ref(false);
const busy = ref(false);
const notice = ref<{ ok: boolean; text: string } | null>(null);
const draft = ref("");
const scroller = ref<HTMLElement | null>(null);

const chat = computed(() => data.value?.chat || null);
const messages = computed(() => data.value?.messages || []);

async function load(scroll = false) {
  loading.value = true;
  const el = scroller.value;
  const atBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  try {
    data.value = (await call(`${API}.get_customer_chat`, {
      name: props.name,
    })) as Data;
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not loaded")) };
  } finally {
    loading.value = false;
  }
  if (scroll || atBottom) {
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  }
}

async function takeOver() {
  busy.value = true;
  notice.value = null;
  try {
    await call(`${API}.take_over`, { name: props.name });
    notice.value = {
      ok: true,
      text: __("The chat is yours; the AI stopped and the customer sees you."),
    };
    emit("changed");
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not taken over")) };
  } finally {
    busy.value = false;
  }
  await load(true);
}

async function send() {
  const text = draft.value.trim();
  if (!text || sending.value) return;
  sending.value = true;
  notice.value = null;
  try {
    await call(`${API}.send_reply`, { name: props.name, text });
    if (draft.value.trim() === text) draft.value = "";
    emit("changed");
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not sent")) };
  } finally {
    sending.value = false;
  }
  await load(true);
}

function openTicket(ticket: string) {
  if (ticket)
    router.push({ name: "TicketAgent", params: { ticketId: ticket } });
}

function placeOf(m: Message) {
  if (m.from === "System") return "justify-center";
  return m.from === "Customer" ? "justify-start" : "justify-end";
}

function bubbleOf(m: Message) {
  if (m.from === "Customer") return "bg-surface-gray-2";
  return m.from === "Assistant" ? "bg-surface-blue-1" : "bg-surface-green-1";
}

function whoOf(m: Message) {
  if (m.from === "Customer") return chat.value?.user || __("Customer");
  if (m.from === "Assistant") return __("AI");
  return m.card?.title || __("TBO Support");
}

function timeOf(stamp: string) {
  return stamp ? dateFormat(stamp, "D MMM, HH:mm") : "";
}

const { $socket } = globalStore();
function onLive(event: { conversation: string }) {
  if (event?.conversation === props.name && !sending.value) load();
}

let timer: number | undefined;
onMounted(() => {
  load(true);
  $socket?.on("helpdesk:customer-chat", onLive);
  timer = window.setInterval(() => {
    if (!sending.value) load();
  }, REFRESH_MS);
});
onBeforeUnmount(() => {
  $socket?.off("helpdesk:customer-chat", onLive);
  window.clearInterval(timer);
});
</script>
