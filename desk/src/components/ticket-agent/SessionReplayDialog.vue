<template>
  <Dialog v-model:open="open" :title="__('What the customer did')" size="7xl">
    <div class="flex flex-col gap-3">
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Recorded in the customer's browser before they raised the ticket. Numbers and typed values are masked."
          )
        }}
      </p>

      <div
        v-if="state === 'loading'"
        class="flex h-[60vh] items-center justify-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 text-sm text-ink-gray-6"
        role="status"
        aria-live="polite"
      >
        <LoadingIndicator class="size-4" />
        {{ __("Loading the replay…") }}
      </div>

      <div
        v-else-if="state === 'error'"
        role="alert"
        class="flex h-[60vh] flex-col items-center justify-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-6 text-center"
      >
        <div class="flex items-start gap-2 text-p-sm text-ink-gray-7">
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0 text-danger"
            aria-hidden="true"
          />
          <span>{{ errorMessage }}</span>
        </div>
        <Button :label="__('Try again')" @click="start" />
      </div>

      <!-- rrweb-player renders its own DOM in here -->
      <div
        v-show="state === 'ready'"
        ref="stage"
        class="session-replay-stage w-full overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-1"
      />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import {
  fetchReplayEvents,
  loadRrwebPlayer,
  ReplayError,
  replayMarkerColors,
  type RrwebPlayer,
} from "@/composables/sessionReplay";
import { __ } from "@/translation";
import { Button, Dialog, LoadingIndicator } from "frappe-ui";
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";

const props = defineProps<{
  replayUrl: string;
}>();

const open = defineModel<boolean>("open", { default: false });

// the player's controller bar sits under the frame
const CONTROLLER_HEIGHT = 80;

const stage = ref<HTMLElement | null>(null);
const state = ref<"idle" | "loading" | "ready" | "error">("idle");
const errorMessage = ref("");
let player: RrwebPlayer | null = null;
// a newer start() (or closing) makes an in-flight one stop before mounting
let attempt = 0;

function destroyPlayer() {
  player?.pause?.();
  player?.$destroy?.();
  player = null;
  if (stage.value) stage.value.innerHTML = "";
}

async function start() {
  const current = ++attempt;
  destroyPlayer();
  state.value = "loading";
  try {
    const [Player, events] = await Promise.all([
      loadRrwebPlayer(),
      fetchReplayEvents(props.replayUrl),
    ]);
    if (current !== attempt || !open.value) return;

    state.value = "ready";
    await nextTick();
    if (!stage.value) return;
    const width = stage.value.clientWidth || 960;
    const height = Math.max(
      240,
      Math.min(
        Math.round((width * 9) / 16),
        window.innerHeight - 260 - CONTROLLER_HEIGHT
      )
    );
    player = new Player({
      target: stage.value,
      props: {
        events,
        width,
        height,
        autoPlay: true,
        skipInactive: true,
        showController: true,
        tags: replayMarkerColors(),
      },
    });
  } catch (error) {
    if (current !== attempt) return;
    errorMessage.value =
      error instanceof ReplayError
        ? error.message
        : __("The replay could not be played.");
    state.value = "error";
  }
}

watch(
  open,
  (isOpen) => {
    if (isOpen) {
      start();
    } else {
      attempt++;
      destroyPlayer();
      state.value = "idle";
    }
  },
  { immediate: true }
);

onBeforeUnmount(destroyPlayer);
</script>

<style scoped>
/* rrweb-player ships light-only chrome; keep its frame on the theme surface */
.session-replay-stage :deep(.rr-player) {
  @apply mx-auto bg-surface-base shadow-none;
}
</style>
