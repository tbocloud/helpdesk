<template>
  <!-- speech to text through the browser's speech service (Web Speech API; Chrome sends the
       audio to Google's). The audio never reaches TBO's servers or the AI, and it costs no
       tokens. -->
  <!-- `contents`: the controls sit in the parent's row and the message wraps to its own line
       below it (the parent's row wraps) -->
  <div class="contents">
    <div class="flex items-center gap-1">
      <Button
        variant="ghost"
        :label="
          listening ? __('Stop listening') : __('Speak instead of typing')
        "
        :aria-pressed="listening"
        :disabled="!supported || disabled"
        :tooltip="
          supported
            ? listening
              ? __('Listening… (Esc to stop)')
              : PRIVACY
            : __('Voice input works in Chrome and Edge, not in this browser')
        "
        :class="listening ? 'ring-2 ring-highlight' : ''"
        @click="listening ? stop() : start()"
      >
        <template #icon>
          <LucideMicOff v-if="!supported" class="size-4" aria-hidden="true" />
          <LucideMic v-else class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <button
        v-if="supported"
        type="button"
        class="min-h-[32px] rounded px-1.5 font-mono text-xs text-ink-gray-6 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :aria-label="
          __(
            'Speech language: {0}',
            lang === 'ml-IN' ? __('Malayalam') : __('English')
          )
        "
        :title="__('Switch the speech language')"
        :disabled="listening"
        @click="lang = lang === 'en-IN' ? 'ml-IN' : 'en-IN'"
      >
        {{ lang === "ml-IN" ? "ML" : "EN" }}
      </button>
      <span v-if="listening" class="text-p-xs text-ink-gray-7" role="status">{{
        __("Listening…")
      }}</span>
    </div>
    <p
      v-if="problem"
      role="alert"
      class="order-last flex basis-full items-start gap-1.5 text-p-xs text-danger"
    >
      <LucideCircleAlert class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      {{ problem }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { onBeforeUnmount, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideMic from "~icons/lucide/mic";
import LucideMicOff from "~icons/lucide/mic-off";

defineProps<{ disabled?: boolean }>();
/** The text so far: what was there before speaking, then what is heard (interim included). */
const text = defineModel<string>({ required: true });

const PRIVACY = __(
  "Uses your browser's speech service (Google in Chrome); nothing is sent to TBO's servers or the AI."
);

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: any) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
const Speech =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
const supported = !!Speech;
const lang = ref<"en-IN" | "ml-IN">("en-IN");
const listening = ref(false);
/** why the last try gave no text, in words */
const problem = ref("");
let recognition: Recognition | null = null;
let before = "";
let heardAny = false;
let failed = false;
let stopped = false;

/** The Web Speech API's error codes, as a person reads them. */
function errorMessage(code: string): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return __(
        "The microphone is blocked for this site. Allow it from the lock icon in the address bar, then try again."
      );
    case "audio-capture":
      return __(
        "No microphone was found. Plug one in or check the system's sound settings."
      );
    case "no-speech":
      return __("Didn't hear anything. Speak after pressing the mic.");
    case "network":
      return __(
        "The browser's speech service couldn't be reached. Check the internet connection, or type instead."
      );
    case "language-not-supported":
      return __(
        "This browser can't recognise that language. Switch to EN, or type instead."
      );
    case "aborted":
      return "";
    default:
      return __("Voice input stopped ({0}). Try again, or type instead.", code);
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") stop();
}

function finish() {
  listening.value = false;
  window.removeEventListener("keydown", onKey);
  recognition = null;
}

function start() {
  if (!supported || listening.value) return;
  problem.value = "";
  heardAny = false;
  failed = false;
  stopped = false;
  const r = new Speech() as Recognition;
  // the language and the options are set before start(), as the API needs
  r.lang = lang.value;
  r.interimResults = true;
  r.continuous = true;
  r.maxAlternatives = 1;
  before = text.value ? `${text.value.trimEnd()} ` : "";
  r.onresult = (e) => {
    let heard = "";
    for (let i = 0; i < e.results.length; i++)
      heard += e.results[i][0].transcript;
    if (heard.trim()) heardAny = true;
    text.value = before + heard.trim();
  };
  r.onerror = (e) => {
    failed = true;
    problem.value = errorMessage(e?.error || "");
  };
  r.onend = () => {
    if (!heardAny && !failed && !stopped)
      problem.value = __(
        "Didn't catch anything. Try again, closer to the mic."
      );
    finish();
  };
  recognition = r;
  listening.value = true;
  window.addEventListener("keydown", onKey);
  try {
    r.start();
  } catch (e) {
    problem.value = errorMessage(String((e as Error)?.name || "start"));
    finish();
  }
}

function stop() {
  // stop() keeps what was heard; onend then tidies up
  stopped = true;
  recognition?.stop();
  listening.value = false;
  window.removeEventListener("keydown", onKey);
}

onBeforeUnmount(() => {
  recognition?.abort();
  finish();
});
</script>
