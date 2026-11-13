<template>
  <!-- the ticket's Copilot chat (Phase 11): where it stands and what you can do now, then the
       conversation (Copilot narrates its work, people write to it), then the box to write in -->
  <div class="flex min-h-0 flex-1 flex-col">
    <div
      v-if="now"
      class="flex gap-2 border-b border-outline-gray-1 bg-surface-gray-1"
      :class="
        wide ? 'flex-wrap items-center px-5 py-2.5' : 'flex-col px-4 py-3'
      "
    >
      <div
        class="flex items-start justify-between gap-2"
        :class="wide && 'min-w-0 flex-1 items-center'"
      >
        <p class="text-base text-ink-gray-8" :class="wide && 'min-w-0 flex-1'">
          <span
            v-if="needsYou"
            class="me-2 rounded-full bg-surface-amber-2 px-2 py-0.5 text-xs font-semibold text-ink-amber-9"
          >
            {{ __("Needs you") }}
          </span>
          <span
            v-else-if="now.state && now.state !== now.line"
            class="mr-1 text-ink-gray-5"
            >{{ now.state }} ·</span
          >
          {{ now.line }}
        </p>
        <Dropdown v-if="now.more.length || now.links.length" :options="menu">
          <Button
            variant="ghost"
            size="sm"
            :aria-label="__('More Copilot actions')"
          >
            <template #icon>
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
      <div v-if="now.actions.length" class="flex flex-wrap gap-1.5">
        <Button
          v-for="(a, i) in now.actions"
          :key="i"
          size="sm"
          :variant="a.style === 'positive' ? 'solid' : 'subtle'"
          :theme="a.style === 'destructive' ? 'red' : 'gray'"
          :loading="busy"
          @click="act(a)"
        >
          {{ a.label }}
        </Button>
      </div>
    </div>

    <p
      v-if="wide && thread.data"
      class="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-outline-gray-1 px-5 py-2 text-sm text-ink-gray-6"
    >
      {{ __("In this chat:") }}
      <span class="text-ink-gray-8">{{ __("Copilot") }}</span>
      <template v-for="p in people" :key="p.user">
        <span aria-hidden="true">·</span>
        <span class="text-ink-gray-8">
          {{ p.name }},
          {{ p.role === "developer" ? __("developer") : __("coordinator") }}
        </span>
      </template>
      <span aria-hidden="true">·</span>
      <span class="text-ink-gray-8">{{ __("Admins") }}</span>
    </p>
    <div
      ref="scroller"
      class="flex-1 space-y-3 overflow-y-auto"
      :class="wide ? 'px-5 py-4' : 'px-4 py-3'"
      aria-live="polite"
    >
      <article
        v-if="wide && request && (request.text || request.subject)"
        class="max-w-3xl rounded-lg border border-outline-gray-2 px-4 py-3"
        :aria-label="__('The customer\'s request')"
      >
        <div
          class="mb-1.5 flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"
        >
          <span class="font-medium text-ink-gray-9">{{ request.who }}</span>
          <span v-if="request.customer">· {{ request.customer }}</span>
          <span v-if="request.at">· {{ when(request.at) }}</span>
          <span
            class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7"
          >
            {{ __("Customer's request") }}
          </span>
        </div>
        <p class="font-medium text-ink-gray-9">{{ request.subject }}</p>
        <p
          v-if="request.text"
          class="mt-1 whitespace-pre-line text-base text-ink-gray-8"
          :class="!requestOpen && 'line-clamp-4'"
        >
          {{ request.text }}
        </p>
        <button
          v-if="request.text.length > 300"
          type="button"
          class="mt-1 text-sm text-ink-gray-6 underline underline-offset-2 hover:text-ink-gray-9"
          :aria-expanded="requestOpen"
          @click="requestOpen = !requestOpen"
        >
          {{ requestOpen ? __("Show less") : __("Show more") }}
        </button>
      </article>
      <p
        v-if="thread.data && !messages.length"
        class="text-p-sm text-ink-gray-6"
      >
        {{
          __(
            "Copilot tells here what it finds and does on this ticket. Ask it anything about the ticket, or tell it what to do."
          )
        }}
      </p>
      <template v-for="m in messages" :key="m.name">
        <p
          v-if="m.direction === 'Out' && m.card?.tone === 'note'"
          class="mx-auto max-w-xl text-center text-sm text-ink-gray-6"
        >
          {{ (m.card.lines || []).join(" ") }}
        </p>
        <div
          v-else
          :class="[
            m.direction === 'In' ? 'flex flex-col items-end' : '',
            wide && 'max-w-3xl',
          ]"
        >
          <span
            v-if="m.direction === 'In'"
            class="mb-0.5 text-xs text-ink-gray-5"
          >
            {{ m.author || __("Someone") }}
            <template v-if="m.via === 'Teams'">
              · {{ __("in Teams") }}</template
            >
            · {{ when(m.at) }}
          </span>
          <span v-else class="mb-0.5 block text-xs text-ink-gray-5">
            {{ __("Copilot") }} · {{ when(m.at) }}
          </span>
          <div
            v-if="m.direction === 'In'"
            class="max-w-[85%] whitespace-pre-line rounded-lg bg-surface-gray-3 px-3 py-2 text-base text-ink-gray-9"
          >
            {{ m.text }}
          </div>
          <CopilotCard
            v-else-if="m.card"
            :card="forThisPerson(m.card)"
            :busy="busy"
            :status="m.status === 'Done' ? __('Done') : null"
            @press="(a, values) => press(a, values, m.name)"
          />
          <div v-else class="text-base text-ink-gray-8">{{ m.text }}</div>
        </div>
      </template>
      <div
        v-if="!thread.data && thread.loading"
        class="h-24 animate-pulse rounded-lg bg-surface-gray-1"
      />
    </div>

    <p
      v-if="now && now.can_write === false"
      class="border-t border-outline-gray-1 px-5 py-3 text-sm text-ink-gray-6"
    >
      {{
        __(
          "Only the developer the ticket is assigned to, its project coordinators and admins can write here. You can read the chat."
        )
      }}
    </p>
    <footer
      v-else
      class="border-t border-outline-gray-1"
      :class="wide ? 'px-5 py-3' : 'p-3'"
    >
      <div v-if="files.length" class="mb-2 flex flex-wrap gap-1">
        <span
          v-for="f in files"
          :key="f.name"
          class="rounded bg-surface-gray-2 px-2 py-0.5 text-sm text-ink-gray-7"
        >
          {{ f.file_name }}
        </span>
      </div>
      <textarea
        v-model="draft"
        rows="2"
        :placeholder="__('Ask Copilot or tell it what to do')"
        :aria-label="__('Ask Copilot or tell it what to do')"
        class="w-full resize-none rounded border-outline-gray-2 text-base"
        @keydown.enter.exact.prevent="send"
      />
      <div class="mt-1.5 flex items-center justify-between">
        <FileUploader
          v-if="thread.data?.chat"
          :upload-args="{
            doctype: 'HDS Copilot Chat',
            docname: thread.data.chat,
            private: true,
          }"
          @success="(f) => files.push(f)"
        >
          <template #default="{ openFileSelector, uploading }">
            <Button
              variant="ghost"
              size="sm"
              :loading="uploading"
              :aria-label="__('Attach a screenshot or a file')"
              @click="openFileSelector()"
            >
              <template #icon><LucidePaperclip class="size-4" /></template>
            </Button>
          </template>
        </FileUploader>
        <Button
          variant="solid"
          size="sm"
          :loading="busy"
          :disabled="!draft.trim() && !files.length"
          @click="send"
        >
          {{ __("Send") }}
        </Button>
      </div>
    </footer>

    <Dialog
      v-model="asking.open"
      :options="{ title: asking.action?.label || '', size: 'sm' }"
    >
      <template #body-content>
        <FormControl
          v-model="asking.value"
          type="textarea"
          :label="asking.label"
          :placeholder="asking.placeholder"
        />
      </template>
      <template #actions>
        <Button
          variant="solid"
          class="w-full"
          :loading="busy"
          :disabled="!asking.value.trim()"
          @click="submitAsked"
        >
          {{ asking.action?.label }}
        </Button>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import CopilotCard, {
  type CopilotAction,
  type CopilotCardData,
} from "@/components/copilot/CopilotCard.vue";
import { globalStore } from "@/stores/globalStore";
import type { TicketRequest } from "./ticketRequest";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  Dialog,
  Dropdown,
  FileUploader,
  FormControl,
  toast,
  dayjs,
} from "frappe-ui";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePaperclip from "~icons/lucide/paperclip";

type ThreadMessage = {
  name: string;
  direction: "In" | "Out";
  author: string;
  via: string;
  text: string;
  card: CopilotCardData | null;
  status: string | null;
  at: string;
};
type Now = {
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
type Person = { user: string; name: string; role: "developer" | "coordinator" };

const props = defineProps<{
  ticket: string;
  /** the ticket page's main view (Phase 12): the customer's request on top, who is in the chat */
  wide?: boolean;
  request?: TicketRequest | null;
}>();
const API = "helpdesk.api.copilot_thread";

const thread = createResource({
  url: `${API}.history`,
  makeParams: () => ({ ticket: props.ticket }),
  auto: true,
});
const messages = computed(
  () => (thread.data?.messages as ThreadMessage[] | undefined) || []
);
const now = computed(() => thread.data?.now as Now | undefined);
const people = computed(
  () => (thread.data?.people as Person[] | undefined) || []
);
const needsYou = computed(() => Boolean(now.value?.actions?.length));
const requestOpen = ref(false);

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
function forThisPerson(card: CopilotCardData): CopilotCardData {
  if (now.value?.can_write !== false || !card.actions?.length) return card;
  return {
    ...card,
    actions: card.actions.filter((a) => OPEN_VERBS.has(a.verb)),
  };
}

const busy = ref(false);
const draft = ref("");
const files = ref<{ name: string; file_name: string }[]>([]);
const scroller = ref<HTMLElement | null>(null);

function when(at: string) {
  return dayjs(at).format("D MMM, HH:mm");
}

async function call(method: string, params: Record<string, unknown>) {
  busy.value = true;
  try {
    await createResource({ url: `${API}.${method}` }).submit({
      ticket: props.ticket,
      ...params,
    });
  } catch (error) {
    toast.error(errorText(error) || __("Copilot could not do that"));
  } finally {
    busy.value = false;
    thread.reload();
  }
}

async function send() {
  if (!draft.value.trim() && !files.value.length) return;
  const text = draft.value;
  const names = files.value.map((f) => f.name);
  draft.value = "";
  files.value = [];
  await call("send", { text, files: JSON.stringify(names) });
}

function press(
  a: CopilotAction,
  values: Record<string, string>,
  message?: string
) {
  return call("press", {
    verb: a.verb,
    data: JSON.stringify({ ...a.data, ...(message ? { message } : {}) }),
    inputs: JSON.stringify(values),
  });
}

// an action that needs a few words first (a reason, the right root cause) asks for them
const NEEDS: Record<string, { label: string; placeholder?: string }> = {
  reason: { label: __("Why?") },
  root_cause: {
    label: __("The right root cause"),
    placeholder: "bug, wrong_setting, customer_mistake, question, …",
  },
};
const asking = reactive({
  open: false,
  action: null as CopilotAction | null,
  value: "",
  label: "",
  placeholder: "",
});
function act(a: CopilotAction) {
  const needs = a.data?.needs as string | undefined;
  if (!needs) return press(a, {});
  asking.action = a;
  asking.value = "";
  asking.label = NEEDS[needs]?.label || needs;
  asking.placeholder =
    needs === "root_cause"
      ? (now.value?.categories || []).join(", ") ||
        NEEDS.root_cause.placeholder ||
        ""
      : "";
  asking.open = true;
}
async function submitAsked() {
  const a = asking.action;
  if (!a) return;
  const needs = a.data.needs as string;
  await press(a, { [needs]: asking.value });
  asking.open = false;
}

const menu = computed(() => [
  ...(now.value?.more || []).map((a) => ({
    label: a.label,
    onClick: () => act(a),
  })),
  ...(now.value?.links || []).map(([label, url]) => ({
    label,
    onClick: () => window.open(url, "_blank", "noopener"),
  })),
]);

// another person's message, Copilot's next step, a decision in Teams: read the chat again
const { $socket } = globalStore();
function onChange(data: { ticket?: string }) {
  if (String(data?.ticket) === String(props.ticket)) thread.reload();
}
onMounted(() => {
  $socket.on("helpdesk:copilot-thread", onChange);
  $socket.on("helpdesk:copilot-run", onChange);
});
onBeforeUnmount(() => {
  $socket.off("helpdesk:copilot-thread", onChange);
  $socket.off("helpdesk:copilot-run", onChange);
});
watch(
  () => props.ticket,
  () => thread.reload()
);
watch(
  () => messages.value.length,
  async () => {
    await nextTick();
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight });
  }
);
</script>
