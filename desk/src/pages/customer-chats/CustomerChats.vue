<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Customer chats')"
      :subtitle="
        __(
          'The Support chat in each customer\'s ERP: watch while the AI talks, then step in.'
        )
      "
    />
    <div class="flex min-h-0 flex-1">
      <section
        class="flex w-full flex-col border-r border-outline-gray-2 md:w-80 md:shrink-0"
        :class="{ 'hidden md:flex': selected }"
        :aria-label="__('Chats')"
      >
        <div class="flex flex-wrap gap-1 px-3 pt-3">
          <Button
            v-for="v in views"
            :key="v.value"
            size="sm"
            :variant="view === v.value ? 'solid' : 'subtle'"
            :label="v.label"
            @click="view = v.value"
          />
        </div>
        <div class="px-3 py-2">
          <TextInput
            v-model="search"
            type="search"
            :placeholder="__('Search customer, user, title or ticket')"
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
            {{ __("No chats here.") }}
          </div>
          <button
            v-for="r in rows"
            :key="r.name"
            type="button"
            class="flex w-full gap-3 border-b border-outline-gray-1 px-3 py-2.5 text-left hover:bg-surface-gray-2"
            :class="{ 'bg-surface-gray-2': selected === r.name }"
            @click="selected = r.name"
          >
            <Avatar :label="r.customer || r.user" size="lg" shape="circle" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span class="truncate text-base text-ink-gray-9">{{
                  r.customer
                }}</span>
                <span class="ml-auto shrink-0 text-xs text-ink-gray-5">{{
                  r.last_message_at ? timeAgo(r.last_message_at) : ""
                }}</span>
              </div>
              <div class="truncate text-p-sm text-ink-gray-7">
                {{ r.user }}{{ r.title ? " · " + r.title : "" }}
              </div>
              <div class="truncate text-p-sm text-ink-gray-6">
                {{ r.last_message || "—" }}
              </div>
              <div class="mt-1 flex flex-wrap items-center gap-1">
                <Badge
                  :label="stateLabel(r.state)"
                  :theme="stateTheme(r.state, r.asked_for_person)"
                  size="sm"
                />
                <Badge
                  v-if="r.ticket"
                  :label="__('Ticket #{0}', r.ticket)"
                  theme="gray"
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
              @click="load(nextCursor)"
            />
          </div>
        </div>
      </section>

      <section
        class="min-w-0 flex-1"
        :class="{ 'hidden md:flex': !selected, flex: selected }"
        :aria-label="__('Chat')"
      >
        <CustomerChatThread
          v-if="selected"
          :key="selected"
          :name="selected"
          class="min-w-0 flex-1"
          @back="selected = ''"
          @changed="refreshList"
        />
        <div
          v-else
          class="flex flex-1 items-center justify-center p-8 text-p-base text-ink-gray-5"
        >
          {{ __("Pick a chat.") }}
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { globalStore } from "@/stores/globalStore";
import { __ } from "@/translation";
import { errorText, timeAgo } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import { Avatar, Badge, Button, TextInput, call, usePageMeta } from "frappe-ui";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import CustomerChatThread from "./CustomerChatThread.vue";

const API = "helpdesk.api.customer_chats";
// live updates do the work; this only covers a lost socket
const REFRESH_MS = 60000;

type Row = {
  name: string;
  customer: string;
  user: string;
  title: string;
  state: string;
  asked_for_person: boolean;
  ticket: string;
  last_message: string;
  last_message_at: string | null;
};

const route = useRoute();
const router = useRouter();

const views = [
  { value: "waiting", label: __("Waiting for a person") },
  { value: "ai", label: __("AI talking") },
  { value: "mine", label: __("Mine") },
  { value: "answered", label: __("Answered by the AI") },
  { value: "all", label: __("All") },
];
const view = ref<string>((route.query.view as string) || "waiting");
const search = ref("");
const selected = ref<string>((route.query.c as string) || "");
const rows = ref<Row[]>([]);
const nextCursor = ref<number | null>(null);
const loading = ref(false);
const loadError = ref("");
// a slower, older answer never overwrites a newer one
let asked = 0;

async function load(cursor = 0) {
  const ask = ++asked;
  loading.value = true;
  try {
    const data = (await call(`${API}.get_customer_chats`, {
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

function stateLabel(state: string) {
  return (
    {
      "AI talking": __("AI talking"),
      "Waiting for a person": __("Waiting for a person"),
      "Ticket raised": __("Ticket raised"),
      "With a person": __("With a person"),
      Closed: __("Closed"),
    }[state] || state
  );
}

function stateTheme(state: string, asked: boolean) {
  if (state === "Waiting for a person" || (asked && state !== "Closed"))
    return "orange";
  if (state === "AI talking") return "blue";
  return "gray";
}

watch([view, selected], () => {
  router.replace({
    query: { ...route.query, view: view.value, c: selected.value || undefined },
  });
});
watch([view, search], refreshList);

const { $socket } = globalStore();
const refreshSoon = useDebounceFn(refreshList, 700);

let timer: number | undefined;
onMounted(() => {
  refreshList();
  // sent to each person who may see the chats (their own room)
  $socket?.on("helpdesk:customer-chat", refreshSoon);
  timer = window.setInterval(refreshList, REFRESH_MS);
});
onBeforeUnmount(() => {
  $socket?.off("helpdesk:customer-chat", refreshSoon);
  window.clearInterval(timer);
});

usePageMeta(() => ({ title: __("Customer chats") }));
</script>
