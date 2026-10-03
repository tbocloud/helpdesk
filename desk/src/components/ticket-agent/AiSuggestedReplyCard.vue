<template>
  <section v-if="visible" class="px-5 py-4" :aria-labelledby="headingId">
    <h2
      :id="headingId"
      class="mb-2.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
    >
      <LucideSparkles class="size-3.5" aria-hidden="true" />
      {{ __("AI suggested reply") }}
    </h2>

    <div aria-live="polite">
      <!-- Drafting -->
      <template v-if="status === 'Pending'">
        <p
          v-if="!pollTimedOut"
          role="status"
          class="flex items-center gap-2 text-sm text-ink-gray-6"
        >
          <LucideLoaderCircle
            class="size-4 shrink-0 animate-spin"
            aria-hidden="true"
          />
          {{ __("Drafting a reply…") }}
        </p>
        <p v-else class="text-sm text-ink-gray-6">
          {{ __("This is taking longer than usual.") }}
          <button
            type="button"
            class="rounded font-medium text-ink-gray-8 underline underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
            @click="checkAgain"
          >
            {{ __("Check again") }}
          </button>
        </p>
      </template>

      <!-- Failed -->
      <p
        v-else-if="status === 'Failed'"
        class="flex items-center gap-1.5 text-sm text-danger"
      >
        <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
        {{ __("Couldn't draft a reply") }}
      </p>

      <!-- Ready -->
      <template v-else-if="status === 'Ready'">
        <div
          :id="previewId"
          class="suggested-reply text-p-sm text-ink-gray-8"
          :class="{ 'max-h-[6.5rem] overflow-hidden': !expanded }"
          v-html="suggestion.reply"
        />
        <button
          type="button"
          class="-mx-1 mt-1 flex items-center gap-1 rounded px-1 text-xs font-medium text-ink-gray-6 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
          :aria-expanded="expanded"
          :aria-controls="previewId"
          @click="expanded = !expanded"
        >
          {{ expanded ? __("Show less") : __("Show full reply") }}
          <LucideChevronDown
            class="size-3.5 transition-transform"
            :class="{ 'rotate-180': expanded }"
            aria-hidden="true"
          />
        </button>

        <p
          v-if="suggestion.note"
          class="mt-2.5 flex items-start gap-1.5 text-xs text-ink-gray-6"
        >
          <LucideInfo class="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 break-words">
            <span class="sr-only">{{ __("Note for the agent:") }}</span>
            {{ suggestion.note }}
          </span>
        </p>

        <ul
          v-if="sourceChips.length"
          class="mt-2.5 flex flex-wrap gap-1"
          :aria-label="__('Based on')"
        >
          <li v-for="chip in sourceChips" :key="chip.key" class="min-w-0">
            <a
              v-if="chip.url"
              :href="chip.url"
              target="_blank"
              rel="noopener"
              class="block max-w-[14rem] truncate rounded bg-surface-gray-2 px-1.5 py-0.5 text-2xs text-ink-gray-7 hover:bg-surface-gray-3 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
              :title="chip.label"
            >
              {{ chip.label }}
            </a>
            <span
              v-else
              class="block max-w-[14rem] truncate rounded bg-surface-gray-2 px-1.5 py-0.5 text-2xs text-ink-gray-7"
            >
              {{ chip.label }}
            </span>
          </li>
        </ul>

        <p
          v-if="suggestion.generated_at"
          class="mt-2 text-2xs text-ink-gray-5"
          :title="suggestion.generated_at"
        >
          {{ __("Drafted {0}", timeAgo(suggestion.generated_at)) }}
        </p>
      </template>
    </div>

    <!-- Regenerate with optional instructions -->
    <form
      v-if="regenerateOpen"
      class="mt-3 flex flex-col gap-2"
      @submit.prevent="regenerate"
    >
      <FormControl
        v-model="instructions"
        type="textarea"
        :rows="2"
        :label="__('What should change? (optional)')"
        :placeholder="__('e.g. Ask for a screenshot of the error')"
        maxlength="1000"
      />
      <div class="flex flex-wrap gap-2">
        <Button
          type="submit"
          :label="__('Draft again')"
          :icon-left="LucideRefreshCw"
          :loading="regenerateResource.loading"
        />
        <Button
          variant="ghost"
          :label="__('Cancel')"
          @click="regenerateOpen = false"
        />
      </div>
    </form>

    <div
      v-else-if="status !== 'Pending' || pollTimedOut"
      class="mt-3 flex flex-wrap gap-2"
    >
      <Button
        v-if="status === 'Ready'"
        variant="solid"
        :label="__('Use this reply')"
        :icon-left="LucideReply"
        @click="useReply"
      />
      <Button
        :label="__('Regenerate')"
        :icon-left="LucideRefreshCw"
        @click="regenerateOpen = true"
      />
    </div>

    <p
      v-if="regenerateError"
      role="alert"
      class="mt-2 flex items-center gap-1.5 text-xs text-danger"
    >
      <LucideCircleAlert class="size-3.5 shrink-0" aria-hidden="true" />
      {{ regenerateError }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { insertIntoReply } from "@/pages/ticket/modalStates";
import { globalStore } from "@/stores/globalStore";
import { __ } from "@/translation";
import { timeAgo } from "@/utils";
import { Button, FormControl, createResource } from "frappe-ui";
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideReply from "~icons/lucide/reply";
import LucideSparkles from "~icons/lucide/sparkles";

type SuggestionStatus = "" | "Pending" | "Ready" | "Failed";

interface SuggestionSource {
  kind: "triage" | "replay" | "investigation" | "article";
  name?: string;
  title?: string;
  url?: string;
}

interface Suggestion {
  status: SuggestionStatus;
  reply: string;
  note: string;
  generated_at: string;
  sources: SuggestionSource[];
}

const POLL_INTERVAL_MS = 5000;
// a thinking model can take a while, but not this long
const POLL_TIMEOUT_MS = 2 * 60 * 1000;
const REALTIME_EVENT = "helpdesk:ai-suggestion";

const props = defineProps<{
  ticketId: string;
}>();

const headingId = `ai-suggestion-${useId()}`;
const previewId = `${headingId}-preview`;
const expanded = ref(false);
const regenerateOpen = ref(false);
const instructions = ref("");
const regenerateError = ref("");
const pollTimedOut = ref(false);

const suggestionResource = createResource({
  url: "helpdesk.api.ai_suggestion.get_suggestion",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: Boolean(props.ticketId),
});

const suggestion = computed<Suggestion>(
  () =>
    (suggestionResource.data as Suggestion | undefined) ?? {
      status: "",
      reply: "",
      note: "",
      generated_at: "",
      sources: [],
    }
);
const status = computed(() => suggestion.value.status);
const visible = computed(() =>
  ["Pending", "Ready", "Failed"].includes(status.value)
);

const SOURCE_LABELS: Record<
  Exclude<SuggestionSource["kind"], "article">,
  string
> = {
  triage: __("Triage"),
  replay: __("Session replay"),
  investigation: __("ERP investigation"),
};

const sourceChips = computed(() =>
  suggestion.value.sources.map((source, index) => ({
    key: `${source.kind}-${source.name ?? index}`,
    label:
      source.kind === "article"
        ? __("KB: {0}", source.title || source.name || "")
        : SOURCE_LABELS[source.kind] ?? source.kind,
    url: source.kind === "article" ? source.url : undefined,
  }))
);

function useReply() {
  insertIntoReply(props.ticketId, suggestion.value.reply);
}

const regenerateResource = createResource({
  url: "helpdesk.api.ai_suggestion.regenerate_suggestion",
  makeParams: () => ({
    ticket: props.ticketId,
    instructions: instructions.value,
  }),
  onSuccess: (data: Suggestion) => {
    suggestionResource.setData(data);
    regenerateOpen.value = false;
    instructions.value = "";
    expanded.value = false;
  },
  onError: (error: { messages?: string[] }) => {
    regenerateError.value =
      error?.messages?.[0] || __("Couldn't start drafting a reply. Try again.");
  },
});

function regenerate() {
  if (regenerateResource.loading) return;
  regenerateError.value = "";
  // onError already shows the message inline
  regenerateResource.submit().catch(() => {});
}

// ─── Polling while a draft is on its way ─────────────────────────
let pollTimer: ReturnType<typeof setInterval> | null = null;
let pollStartedAt = 0;

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function startPolling() {
  stopPolling();
  pollTimedOut.value = false;
  pollStartedAt = Date.now();
  pollTimer = setInterval(() => {
    if (Date.now() - pollStartedAt >= POLL_TIMEOUT_MS) {
      stopPolling();
      pollTimedOut.value = true;
      return;
    }
    suggestionResource.reload();
  }, POLL_INTERVAL_MS);
}

function checkAgain() {
  suggestionResource.reload();
  startPolling();
}

watch(
  status,
  (value) => {
    if (value === "Pending") startPolling();
    else {
      stopPolling();
      pollTimedOut.value = false;
    }
  },
  { immediate: true }
);

watch(
  () => props.ticketId,
  (ticketId, previous) => {
    if (!ticketId || ticketId === previous) return;
    expanded.value = false;
    regenerateOpen.value = false;
    regenerateError.value = "";
    suggestionResource.reload();
  }
);

// Triage and investigations finish in the background: the server announces
// new drafts so an open ticket shows them without a refresh
const { $socket } = globalStore();

function onSuggestionEvent(data: { ticket_id?: string }) {
  if (String(data?.ticket_id) === String(props.ticketId)) {
    suggestionResource.reload();
  }
}

onMounted(() => $socket.on(REALTIME_EVENT, onSuggestionEvent));

onBeforeUnmount(() => {
  stopPolling();
  $socket.off(REALTIME_EVENT, onSuggestionEvent);
});
</script>

<style scoped>
.suggested-reply :deep(p + p) {
  @apply mt-2;
}
.suggested-reply :deep(a) {
  @apply break-all text-ink-gray-9 underline underline-offset-2;
}
</style>
