<template>
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :aria-label="__('Working on now')"
  >
    <h2 class="text-base font-semibold text-ink-gray-9">
      {{ __("Working on now") }}
    </h2>

    <p v-if="!task" class="mt-3 text-p-sm text-ink-gray-6">
      {{
        __(
          "Nothing in progress. Start a task from the list and its timer runs here."
        )
      }}
    </p>

    <template v-else>
      <p class="mt-3 break-words text-base-medium text-ink-gray-9">
        {{ task.title }}
        <KeyTag v-if="task.is_key" class="ml-1 align-middle" />
      </p>
      <p class="mt-0.5 truncate text-p-sm text-ink-gray-5">
        {{ task.project_name || task.project }} ·
        <span class="font-mono text-xs tabular-nums">{{ task.name }}</span>
      </p>

      <div
        v-if="timer.loading && !timer.data"
        class="mt-3 h-8 w-32 animate-pulse rounded bg-surface-gray-3"
        role="status"
        :aria-label="__('Loading')"
      />
      <p
        v-else-if="timer.error"
        class="mt-3 flex items-center gap-1.5 text-p-sm text-danger"
        role="alert"
      >
        <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
        {{ __("Couldn't load the timer.") }}
        <Button size="sm" :label="__('Retry')" @click="timer.reload()" />
      </p>
      <template v-else>
        <p
          v-if="running"
          class="mt-3 font-mono text-3xl tabular-nums text-ink-gray-9"
        >
          {{ clock }}
        </p>
        <p class="text-p-sm text-ink-gray-5" :class="running ? '' : 'mt-3'">
          {{
            running
              ? __("Timer running since you last started it")
              : __("Timer paused. Resume when you pick it up.")
          }}
        </p>
      </template>

      <div class="mt-4 flex flex-wrap gap-2">
        <Button
          v-if="running"
          :label="__('Pause')"
          :loading="stop.loading"
          @click="stop.submit({ task: task.name })"
        >
          <template #prefix>
            <LucidePause class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-else-if="timer.data"
          :label="__('Resume')"
          :loading="resume.loading"
          @click="resume.submit({ task: task.name })"
        >
          <template #prefix>
            <LucidePlay class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          variant="solid"
          :label="__('Complete')"
          :disabled="!!task.waiting_on"
          @click="emit('complete', task)"
        />
      </div>
      <p v-if="more" class="mt-3 text-p-xs text-ink-gray-5">
        {{ __("{0} more in progress", String(more)) }}
      </p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useNow } from "@vueuse/core";
import { Button, createResource, toast } from "frappe-ui";
import { computed, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePause from "~icons/lucide/pause";
import LucidePlay from "~icons/lucide/play";
import KeyTag from "./KeyTag.vue";
import type { WorkItem } from "../workMeta";

const props = defineProps<{ items: WorkItem[] }>();
const emit = defineEmits<{ complete: [item: WorkItem]; changed: [] }>();

const working = computed(() =>
  props.items.filter((i) => i.kind === "task" && i.status === "Working")
);

interface Timer {
  running: boolean;
  elapsed: number;
}

const timer = createResource({
  url: "helpdesk.tasky.api.get_timer",
  makeParams: () => ({ task: task.value?.name }),
});

// the first task in progress; with several, the rest are counted below
const task = computed<WorkItem | null>(() => working.value[0] ?? null);
const more = computed(() => Math.max(working.value.length - 1, 0));

const loadedAt = computed(() => (timer.data ? Date.now() : 0));
const now = useNow({ interval: 1000 });
const running = computed(() => !!(timer.data as Timer | undefined)?.running);

const clock = computed(() => {
  const t = timer.data as Timer | undefined;
  if (!t) return "00:00:00";
  const base = t.elapsed * 3600;
  const live = t.running
    ? Math.max((now.value.getTime() - loadedAt.value) / 1000, 0)
    : 0;
  const total = Math.floor(base + live);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(total / 3600))}:${pad(
    Math.floor((total % 3600) / 60)
  )}:${pad(total % 60)}`;
});

watch(
  () => task.value?.name,
  (name) => {
    if (name) timer.fetch();
  },
  { immediate: true }
);

function done() {
  timer.reload();
  emit("changed");
}

const stop = createResource({
  url: "helpdesk.tasky.api.stop_timer",
  onSuccess: done,
  onError: (e: unknown) =>
    toast.error(errorText(e, __("Couldn't pause the timer."))),
});

const resume = createResource({
  url: "helpdesk.tasky.api.start_timer",
  onSuccess: done,
  onError: (e: unknown) =>
    toast.error(errorText(e, __("Couldn't resume the timer."))),
});
</script>
