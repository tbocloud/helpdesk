<template>
  <div class="flex min-w-0 flex-col gap-1">
    <button
      v-if="lazy && !started"
      type="button"
      class="inline-flex min-h-11 items-center gap-2 self-start rounded-lg border border-outline-gray-2 px-3 text-sm text-ink-gray-8 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      @click="started = true"
    >
      <LucidePlay class="size-4" aria-hidden="true" />
      {{ __("Play recording") }}
    </button>
    <template v-else>
      <!-- the file is checked as it loads: one that can't be played says so instead of "0:00 / 0:00" -->
      <audio
        v-show="state === 'ready'"
        class="h-11 w-full max-w-md"
        controls
        preload="metadata"
        :autoplay="lazy"
        :src="src"
        :aria-label="__('Recording of this call')"
        @loadedmetadata="onLoaded"
        @error="state = 'missing'"
      />
      <p
        v-if="state === 'loading'"
        class="flex items-center gap-1.5 text-p-sm text-ink-gray-6"
      >
        <LucideAudioLines class="size-4 shrink-0" aria-hidden="true" />
        {{ __("Loading the recording…") }}
      </p>
      <p
        v-else-if="state === 'missing'"
        role="status"
        class="flex items-center gap-1.5 text-p-sm text-ink-gray-6"
      >
        <LucideAudioLines class="size-4 shrink-0" aria-hidden="true" />
        {{ __("Recording not available") }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { ref } from "vue";
import LucideAudioLines from "~icons/lucide/audio-lines";
import LucidePlay from "~icons/lucide/play";

defineProps<{
  src: string;
  /** shows a Play button first and loads the file only when it is tapped */
  lazy?: boolean;
}>();

const started = ref(false);
const state = ref<"loading" | "ready" | "missing">("loading");

function onLoaded(event: Event) {
  const { duration } = event.target as HTMLAudioElement;
  state.value = Number.isFinite(duration) && duration > 0 ? "ready" : "missing";
}
</script>
