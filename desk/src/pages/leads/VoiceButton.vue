<template>
  <!-- speech to text in the browser (Web Speech API): no audio leaves the browser for our
       servers or the AI provider, and it costs no tokens -->
  <div class="flex items-center gap-1">
    <Button
      variant="ghost"
      :label="listening ? __('Stop listening') : __('Speak instead of typing')"
      :aria-pressed="listening"
      :disabled="!supported || disabled"
      :tooltip="
        supported
          ? listening
            ? __('Listening… (Esc to stop)')
            : __('Speak; you can edit the text before sending')
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
      @click="lang = lang === 'en-IN' ? 'ml-IN' : 'en-IN'"
    >
      {{ lang === "ml-IN" ? "ML" : "EN" }}
    </button>
    <span v-if="listening" class="text-p-xs text-ink-gray-7" role="status">{{
      __("Listening…")
    }}</span>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { onBeforeUnmount, ref } from "vue";
import LucideMic from "~icons/lucide/mic";
import LucideMicOff from "~icons/lucide/mic-off";

defineProps<{ disabled?: boolean }>();
/** The text so far: what was there before speaking, then what is heard (interim included). */
const text = defineModel<string>({ required: true });

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: any) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};
const Speech =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
const supported = !!Speech;
const lang = ref<"en-IN" | "ml-IN">("en-IN");
const listening = ref(false);
let recognition: Recognition | null = null;
let before = "";

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") stop();
}

function start() {
  if (!supported || listening.value) return;
  recognition = new Speech() as Recognition;
  recognition.lang = lang.value;
  recognition.interimResults = true;
  recognition.continuous = true;
  before = text.value ? `${text.value.trimEnd()} ` : "";
  recognition.onresult = (e) => {
    let heard = "";
    for (let i = 0; i < e.results.length; i++)
      heard += e.results[i][0].transcript;
    text.value = before + heard.trim();
  };
  recognition.onend = recognition.onerror = () => {
    listening.value = false;
    window.removeEventListener("keydown", onKey);
  };
  listening.value = true;
  window.addEventListener("keydown", onKey);
  recognition.start();
}

function stop() {
  recognition?.stop();
  listening.value = false;
  window.removeEventListener("keydown", onKey);
}

onBeforeUnmount(stop);
</script>
