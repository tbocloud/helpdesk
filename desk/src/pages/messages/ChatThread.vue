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
            {{ chat.contact_name }}
          </div>
          <div class="flex flex-wrap items-center gap-1">
            <Badge :label="chat.channel" theme="gray" size="sm" />
            <Badge
              :label="stateLabel(chat.state)"
              :theme="chat.state === 'AI talking' ? 'blue' : 'gray'"
              size="sm"
            />
            <Badge
              v-if="chat.window"
              :label="windowText"
              :theme="chat.window.open ? 'green' : 'red'"
              size="sm"
            />
          </div>
        </div>
        <div v-if="chat" class="flex flex-wrap gap-2">
          <Button
            v-if="chat.state === 'AI talking'"
            :label="__('I\'ll answer')"
            :loading="busy === 'take'"
            @click="takeOver"
          />
          <Button
            v-if="data?.can_move_to_support"
            :label="__('Move to Support')"
            :loading="busy === 'move'"
            @click="confirmMove = true"
          />
          <Button
            v-if="chat.ticket"
            variant="ghost"
            :label="__('Ticket #{0}', chat.ticket)"
            @click="openTicket"
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
          <!-- Chatwoot's own lines and the system's -->
          <div
            v-if="m.kind === 'Activity' || m.from === 'System'"
            class="max-w-[80%] text-center text-xs text-ink-gray-5"
          >
            {{ m.text }} · {{ timeOf(m.sent_at) }}
          </div>
          <div
            v-else
            class="max-w-[80%] rounded-xl px-3 py-2"
            :class="bubbleOf(m)"
          >
            <div class="mb-0.5 text-xs text-ink-gray-5">
              {{ whoOf(m) }} · {{ timeOf(m.sent_at) }}
            </div>
            <div
              v-if="m.text"
              class="whitespace-pre-wrap break-words text-p-base text-ink-gray-9"
            >
              {{ m.text }}
            </div>
            <div v-for="(f, i) in m.files" :key="i" class="mt-1">
              <a
                v-if="f.type === 'Image' && f.url"
                :href="f.url"
                target="_blank"
                rel="noopener"
              >
                <img
                  :src="f.url"
                  :alt="f.name || __('Picture')"
                  class="max-h-60 rounded-lg"
                />
              </a>
              <audio
                v-else-if="f.type === 'Audio' && f.url"
                :src="f.url"
                controls
                class="max-w-full"
              />
              <video
                v-else-if="f.type === 'Video' && f.url"
                :src="f.url"
                controls
                class="max-h-60 max-w-full rounded-lg"
              />
              <a
                v-else-if="f.url"
                :href="f.url"
                target="_blank"
                rel="noopener"
                class="text-p-sm text-ink-blue-3 underline"
                >{{ f.name || __("File") }}</a
              >
              <a
                v-else-if="f.link"
                :href="f.link"
                target="_blank"
                rel="noopener noreferrer"
                class="text-p-sm text-ink-blue-3 underline"
                >{{ f.note || __("Location") }}</a
              >
              <div v-else class="text-p-sm italic text-ink-gray-6">
                {{ f.note || __("{0} (not kept)", f.type) }}
              </div>
            </div>
            <div
              v-if="m.direction === 'Out' && m.kind !== 'Note' && m.status"
              class="mt-0.5 text-right text-xs"
              :class="
                m.status === 'Failed'
                  ? 'text-ink-red-4'
                  : m.status === 'Read'
                  ? 'font-medium text-ink-gray-7'
                  : 'text-ink-gray-6'
              "
              :title="m.error"
            >
              {{ statusText(m) }}
            </div>
          </div>
        </div>
      </div>

      <!-- reply box -->
      <div class="border-t border-outline-gray-2 px-4 py-3">
        <div
          v-if="windowClosed && !asNote"
          class="mb-2 rounded-lg bg-surface-amber-1 px-3 py-2 text-p-sm text-ink-gray-8"
        >
          {{
            __(
              "The 24-hour window closed {0}. This channel takes only an approved template now (templates come in the next update). You can still add an internal note.",
              closedWhen
            )
          }}
        </div>
        <textarea
          v-model="draft"
          rows="3"
          class="w-full resize-y rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-p-base text-ink-gray-9 focus:border-outline-gray-4 focus:outline-none"
          :class="{ 'bg-surface-amber-1': asNote }"
          :placeholder="
            asNote
              ? __('An internal note, for staff only')
              : __('Reply to the customer (Ctrl+Enter sends)')
          "
          :disabled="sending || (windowClosed && !asNote)"
          @keydown.enter.ctrl.prevent="send"
          @keydown.enter.meta.prevent="send"
        />
        <div class="mt-2 flex items-center gap-3">
          <label class="flex items-center gap-2 text-p-sm text-ink-gray-7">
            <input v-model="asNote" type="checkbox" />
            {{ __("Internal note") }}
          </label>
          <span
            v-if="!asNote && chat?.state === 'AI talking'"
            class="text-p-sm text-ink-gray-5"
          >
            {{ __("Sending takes the chat over from the AI.") }}
          </span>
          <Button
            class="ml-auto"
            variant="solid"
            :label="asNote ? __('Add note') : __('Send')"
            :loading="sending"
            :disabled="!draft.trim() || (windowClosed && !asNote)"
            @click="send"
          />
        </div>
      </div>
    </div>

    <!-- context -->
    <aside
      v-if="data"
      class="hidden w-72 shrink-0 overflow-y-auto border-l border-outline-gray-2 px-4 py-3 lg:block"
      :aria-label="__('About this chat')"
    >
      <div class="mb-4">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("Contact") }}
        </div>
        <div class="text-base text-ink-gray-9">
          {{ data.contact.name || "—" }}
        </div>
        <div v-if="data.contact.phone" class="text-p-sm text-ink-gray-7">
          {{ data.contact.phone }}
        </div>
        <div v-if="data.contact.email" class="text-p-sm text-ink-gray-7">
          {{ data.contact.email }}
        </div>
        <div v-if="data.contact.customer" class="text-p-sm text-ink-gray-7">
          {{ __("Customer") }}: {{ data.contact.customer }}
        </div>
        <div
          v-if="!data.contact.verified"
          class="mt-1 text-xs italic text-ink-gray-6"
        >
          {{ __("The email or phone was typed in the chat; not verified.") }}
        </div>
      </div>
      <div v-if="data.ticket" class="mb-4">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("Ticket") }}
        </div>
        <button
          type="button"
          class="text-left text-base text-ink-blue-3 underline"
          @click="openTicket"
        >
          #{{ data.ticket.name }} {{ data.ticket.subject }}
        </button>
        <div class="text-p-sm text-ink-gray-7">
          {{ data.ticket.status }} · {{ data.ticket.priority }}
        </div>
        <div v-if="data.ticket.team" class="text-p-sm text-ink-gray-7">
          {{ __("Team") }}: {{ data.ticket.team }}
        </div>
        <div class="text-p-sm text-ink-gray-7">
          {{ __("With") }}:
          {{
            data.ticket.assignees.map((a) => a.name).join(", ") ||
            __("nobody yet")
          }}
        </div>
      </div>
      <div v-if="data.earlier.length">
        <div class="mb-1 text-xs uppercase text-ink-gray-5">
          {{ __("Earlier tickets") }}
        </div>
        <button
          v-for="t in data.earlier"
          :key="t.name"
          type="button"
          class="block text-left text-p-sm text-ink-blue-3 underline"
          @click="openTicket(t.name)"
        >
          #{{ t.name }} {{ t.subject }} ({{ t.status }})
        </button>
      </div>
    </aside>

    <Dialog
      v-model="confirmMove"
      :options="{
        title: __('Move to Support?'),
        message: __(
          'For a customer\'s ERP problem: the ticket goes to the customer\'s own people, and Copilot and triage may start. Replies still go back on this channel.'
        ),
        actions: [
          {
            label: __('Move to Support'),
            variant: 'solid',
            onClick: moveToSupport,
          },
        ],
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import { Badge, Button, Dialog, call, dayjs } from "frappe-ui";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRouter } from "vue-router";

const API = "helpdesk.api.messages";
const REFRESH_MS = 10000;

type FileItem = {
  type: string;
  url: string;
  name: string;
  size: number;
  note: string;
  link: string;
};
type Message = {
  name: string;
  direction: "In" | "Out";
  from: "Customer" | "AI" | "Staff" | "System";
  author: string;
  kind: "Text" | "Template" | "Note" | "Activity";
  text: string;
  sent_at: string;
  status: string;
  error: string;
  files: FileItem[];
};
type Conversation = {
  name: string;
  contact_name: string;
  channel: string;
  state: string;
  ticket: string;
  window: { open: boolean; closes_at: string | null } | null;
};
type Data = {
  conversation: Conversation;
  contact: {
    name: string;
    email: string;
    phone: string;
    customer: string;
    verified: boolean;
  };
  ticket: {
    name: string;
    subject: string;
    status: string;
    priority: string;
    team: string;
    assignees: { user: string; name: string }[];
  } | null;
  earlier: { name: string; subject: string; status: string }[];
  messages: Message[];
  can_move_to_support: boolean;
};

const props = defineProps<{ name: string }>();
const emit = defineEmits<{ (e: "back"): void; (e: "changed"): void }>();
const router = useRouter();

const data = ref<Data | null>(null);
const loading = ref(false);
const sending = ref(false);
const busy = ref<"" | "take" | "move">("");
const notice = ref<{ ok: boolean; text: string } | null>(null);
const draft = ref("");
const asNote = ref(false);
const confirmMove = ref(false);
const scroller = ref<HTMLElement | null>(null);

const chat = computed(() => data.value?.conversation || null);
const messages = computed(() => data.value?.messages || []);
const windowClosed = computed(
  () => !!chat.value?.window && !chat.value.window.open
);
const closedWhen = computed(() =>
  chat.value?.window?.closes_at
    ? dayjs(chat.value.window.closes_at).fromNow()
    : ""
);
const windowText = computed(() => {
  const w = chat.value?.window;
  if (!w) return "";
  if (!w.open) return __("Window closed");
  const hours = Math.max(dayjs(w.closes_at).diff(dayjs(), "hour"), 0);
  return hours < 1 ? __("Closes soon") : __("Closes in {0} h", String(hours));
});

async function load(scroll = false) {
  loading.value = true;
  const atBottom = isAtBottom();
  try {
    data.value = (await call(`${API}.get_conversation`, {
      name: props.name,
    })) as Data;
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not loaded")) };
  } finally {
    loading.value = false;
  }
  // a new message scrolls into view only when the person was already at the bottom
  if (scroll || atBottom) await scrollToEnd();
}

function isAtBottom() {
  const el = scroller.value;
  return !el || el.scrollHeight - el.scrollTop - el.clientHeight < 40;
}

async function scrollToEnd() {
  await nextTick();
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

async function send() {
  const text = draft.value.trim();
  if (!text || sending.value || (windowClosed.value && !asNote.value)) return;
  sending.value = true;
  notice.value = null;
  try {
    await call(`${API}.send_message`, {
      name: props.name,
      text,
      private: asNote.value ? 1 : 0,
    });
    // only what was sent is cleared: text typed meanwhile stays
    if (draft.value.trim() === text) draft.value = "";
    emit("changed");
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not sent")) };
  } finally {
    sending.value = false;
  }
  await load(true);
}

async function takeOver() {
  busy.value = "take";
  notice.value = null;
  try {
    await call(`${API}.take_over`, { name: props.name });
    notice.value = { ok: true, text: __("The chat is yours; the AI stopped.") };
    emit("changed");
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not taken over")) };
  } finally {
    busy.value = "";
  }
  await load();
}

async function moveToSupport() {
  confirmMove.value = false;
  if (!chat.value?.ticket) return;
  busy.value = "move";
  notice.value = null;
  try {
    await call(`${API}.move_to_support`, { ticket: chat.value.ticket });
    emit("changed");
    router.push({
      name: "TicketAgent",
      params: { ticketId: chat.value.ticket },
    });
  } catch (err) {
    notice.value = { ok: false, text: errorText(err, __("Not moved")) };
  } finally {
    busy.value = "";
  }
}

function openTicket(name?: string | Event) {
  const ticket = typeof name === "string" ? name : chat.value?.ticket;
  if (ticket)
    router.push({ name: "TicketAgent", params: { ticketId: ticket } });
}

function placeOf(m: Message) {
  if (m.kind === "Activity" || m.from === "System") return "justify-center";
  return m.direction === "In" ? "justify-start" : "justify-end";
}

function bubbleOf(m: Message) {
  if (m.kind === "Note") return "bg-surface-amber-1";
  if (m.direction === "In") return "bg-surface-gray-2";
  return m.from === "AI" ? "bg-surface-blue-1" : "bg-surface-green-1";
}

function whoOf(m: Message) {
  if (m.kind === "Note") return __("Note by {0}", m.author || __("staff"));
  if (m.from === "Customer") return chat.value?.contact_name || __("Customer");
  if (m.from === "AI") return __("AI");
  if (m.kind === "Template")
    return __("Template by {0}", m.author || __("staff"));
  return m.author || __("Staff");
}

function statusText(m: Message) {
  if (m.status === "Failed")
    return __("Failed: {0}", m.error || __("no reason given"));
  return { Sent: "✓", Delivered: "✓✓", Read: __("✓✓ Read") }[m.status] || "";
}

function stateLabel(state: string) {
  return (
    {
      "AI talking": __("AI talking"),
      "With a person": __("With a person"),
      Closed: __("Closed"),
    }[state] || state
  );
}

function timeOf(stamp: string) {
  return stamp ? dateFormat(stamp, "D MMM, HH:mm") : "";
}

let timer: number | undefined;
onMounted(() => {
  load(true);
  // live updates come with step 5; until then the chat refreshes itself
  timer = window.setInterval(() => {
    if (!sending.value) load();
  }, REFRESH_MS);
});
onBeforeUnmount(() => window.clearInterval(timer));
watch(asNote, () => (notice.value = null));
</script>
