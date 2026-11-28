<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Messages')"
      :subtitle="
        __(
          'WhatsApp, Instagram, Facebook and the website chat: the AI answers first, then you.'
        )
      "
    >
      <template #right-header>
        <Button
          v-if="canNotify"
          size="sm"
          :variant="notifyOn ? 'subtle' : 'solid'"
          :icon-left="notifyOn ? 'lucide-bell' : 'lucide-bell-off'"
          :label="notifyOn ? __('Notifications on') : __('Notify me')"
          @click="toggleNotify"
        />
      </template>
    </LayoutHeader>
    <div class="flex min-h-0 flex-1">
      <!-- the conversations -->
      <section
        class="flex w-full flex-col border-r border-outline-gray-2 md:w-80 md:shrink-0"
        :class="{ 'hidden md:flex': selected }"
        :aria-label="__('Conversations')"
      >
        <div class="flex flex-wrap gap-1 px-3 pt-3">
          <Button
            v-for="v in views"
            :key="v.value"
            size="sm"
            :variant="view === v.value ? 'solid' : 'subtle'"
            :label="v.label"
            @click="setView(v.value)"
          />
        </div>
        <div class="px-3 py-2">
          <TextInput
            v-model="search"
            type="search"
            :placeholder="__('Search name, phone, text or ticket')"
            :debounce="400"
          />
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto">
          <div
            v-if="loading && !rows.length"
            class="p-4 text-p-sm text-ink-gray-5"
          >
            {{ __("Loading…") }}
          </div>
          <div
            v-else-if="loadError"
            class="m-3 rounded-lg bg-surface-red-1 px-3 py-2 text-p-sm text-ink-red-4"
          >
            {{ loadError }}
          </div>
          <div v-else-if="!rows.length" class="p-4 text-p-sm text-ink-gray-5">
            {{ __("No conversations here.") }}
          </div>
          <button
            v-for="r in rows"
            :key="r.name"
            type="button"
            class="flex w-full gap-3 border-b border-outline-gray-1 px-3 py-2.5 text-left hover:bg-surface-gray-2"
            :class="{ 'bg-surface-gray-2': selected === r.name }"
            @click="open(r.name)"
          >
            <Avatar :label="r.contact_name" size="lg" shape="circle" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span
                  class="truncate text-base text-ink-gray-9"
                  :class="{ 'font-semibold': r.unread }"
                  >{{ r.contact_name }}</span
                >
                <span
                  v-if="r.unread"
                  class="size-2 shrink-0 rounded-full bg-surface-blue-3"
                  :aria-label="__('Unread')"
                />
                <span class="ml-auto shrink-0 text-xs text-ink-gray-5">{{
                  r.last_message_at ? timeAgo(r.last_message_at) : ""
                }}</span>
              </div>
              <div class="truncate text-p-sm text-ink-gray-6">
                {{ r.last_message || "—" }}
              </div>
              <div class="mt-1 flex flex-wrap items-center gap-1">
                <Badge :label="r.channel" theme="gray" size="sm" />
                <Badge
                  v-if="r.state === 'AI talking'"
                  :label="__('AI talking')"
                  theme="blue"
                  size="sm"
                />
                <Badge
                  v-if="r.window"
                  :label="windowLabel(r.window)"
                  :theme="r.window.open ? 'green' : 'red'"
                  size="sm"
                />
              </div>
            </div>
          </button>
          <div v-if="nextCursor" class="p-3">
            <Button
              :label="__('More')"
              class="w-full"
              :loading="loading"
              @click="loadMore"
            />
          </div>
        </div>
      </section>

      <!-- the chat -->
      <section
        class="min-w-0 flex-1"
        :class="{ 'hidden md:flex': !selected, flex: selected }"
        :aria-label="__('Chat')"
      >
        <ChatThread
          v-if="selected"
          :key="selected"
          :name="selected"
          class="min-w-0 flex-1"
          @back="close"
          @changed="refreshList"
        />
        <div
          v-else
          class="flex flex-1 items-center justify-center p-8 text-p-base text-ink-gray-5"
        >
          {{ __("Pick a conversation.") }}
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { globalStore } from "@/stores/globalStore";
import { useDebounceFn } from "@vueuse/core";
import { __ } from "@/translation";
import { errorText, timeAgo } from "@/utils";
import {
  Avatar,
  Badge,
  Button,
  TextInput,
  call,
  dayjs,
  usePageMeta,
} from "frappe-ui";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChatThread from "./ChatThread.vue";

const API = "helpdesk.api.messages";
// live updates do the work; this only covers a lost socket
const REFRESH_MS = 60000;
const NOTIFY_KEY = "hd-messages-notify";

type Row = {
  name: string;
  contact_name: string;
  channel: string;
  last_message: string;
  last_message_at: string | null;
  unread: boolean;
  state: string;
  window: { open: boolean; closes_at: string | null } | null;
};

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const views = computed(() => {
  const all = [
    { value: "mine", label: __("Mine") },
    { value: "team", label: __("My teams") },
    { value: "unassigned", label: __("Unassigned") },
    { value: "waiting", label: __("Waiting for us") },
    { value: "ai", label: __("AI talking") },
  ];
  if (auth.isAdmin || auth.isManager)
    all.push({ value: "all", label: __("All") });
  return all;
});

const view = ref<string>((route.query.view as string) || "waiting");
const search = ref("");
const selected = ref<string>((route.query.c as string) || "");
const rows = ref<Row[]>([]);
const nextCursor = ref<number | null>(null);

const loading = ref(false);
const loadError = ref("");
// a slower, older answer never overwrites a newer one (a view switched while it loaded)
let asked = 0;

async function load(cursor = 0) {
  const ask = ++asked;
  loading.value = true;
  try {
    const data = (await call(`${API}.get_conversations`, {
      view: view.value,
      search: search.value,
      cursor,
    })) as { data: Row[]; next_cursor: number | null };
    if (ask !== asked) return;
    rows.value = cursor ? [...rows.value, ...data.data] : data.data;
    nextCursor.value = data.next_cursor;
    loadError.value = "";
  } catch (err) {
    if (ask === asked) loadError.value = errorText(err, __("Not loaded"));
  } finally {
    if (ask === asked) loading.value = false;
  }
}

function refreshList() {
  load(0);
}

function loadMore() {
  if (nextCursor.value != null) load(nextCursor.value);
}

function setView(value: string) {
  view.value = value;
}

function open(name: string) {
  selected.value = name;
}

function close() {
  selected.value = "";
}

function windowLabel(window: { open: boolean; closes_at: string | null }) {
  if (!window.open) return __("Window closed");
  const hours = Math.max(dayjs(window.closes_at).diff(dayjs(), "hour"), 0);
  return hours < 1 ? __("Closes soon") : __("Closes in {0} h", String(hours));
}

// the view and the open chat stay in the address, so a link or a reload keeps them
watch([view, selected], () => {
  router.replace({
    query: { ...route.query, view: view.value, c: selected.value || undefined },
  });
});
watch([view, search], refreshList);

// --- live updates and notifications --------------------------------------------------------

const { $socket } = globalStore();
const refreshSoon = useDebounceFn(refreshList, 700);
const canNotify = typeof window !== "undefined" && "Notification" in window;
const notifyOn = ref(readNotify());

// a per-person convenience: remembered in this browser only
function readNotify() {
  try {
    return (
      canNotify &&
      Notification.permission === "granted" &&
      localStorage.getItem(NOTIFY_KEY) === "1"
    );
  } catch {
    return false;
  }
}

async function toggleNotify() {
  if (notifyOn.value) {
    notifyOn.value = false;
  } else {
    const permission =
      Notification.permission === "granted"
        ? "granted"
        : await Notification.requestPermission();
    notifyOn.value = permission === "granted";
  }
  try {
    localStorage.setItem(NOTIFY_KEY, notifyOn.value ? "1" : "0");
  } catch {
    // private window: it lasts for this visit only
  }
}

function onLive(event: { conversation: string; direction: string }) {
  refreshSoon();
  // a customer wrote, and the person isn't looking at that chat: tell them, without the text
  const looking = !document.hidden && selected.value === event?.conversation;
  if (event?.direction === "In" && notifyOn.value && !looking) {
    const note = new Notification(__("New message"), {
      body: __("A customer wrote in Messages."),
      tag: `hd-messages-${event.conversation}`,
    });
    note.onclick = () => {
      window.focus();
      open(event.conversation);
      note.close();
    };
  }
}

let timer: number | undefined;
onMounted(() => {
  refreshList();
  // the server checks this person may read conversations before letting them in
  $socket?.emit("doctype_subscribe", "HD Chat Conversation");
  $socket?.on("helpdesk:chat-message", onLive);
  timer = window.setInterval(refreshList, REFRESH_MS);
});
onBeforeUnmount(() => {
  $socket?.off("helpdesk:chat-message", onLive);
  $socket?.emit("doctype_unsubscribe", "HD Chat Conversation");
  window.clearInterval(timer);
});

usePageMeta(() => ({ title: __("Messages") }));
</script>
