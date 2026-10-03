<template>
  <section
    v-if="replay.data?.available"
    class="px-5 py-4"
    :aria-labelledby="headingId"
  >
    <h2
      :id="headingId"
      class="mb-2.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
    >
      <LucideClapperboard class="size-3.5" aria-hidden="true" />
      {{ __("Session replay") }}
    </h2>

    <Button
      v-if="replay.data.replay_url"
      class="mb-3 w-full"
      :label="__('Watch what the customer did')"
      :icon-left="LucidePlay"
      @click="playerOpen = true"
    />

    <dl v-if="details.length" class="mb-3 flex flex-col gap-1">
      <div
        v-for="row in details"
        :key="row.label"
        class="grid grid-cols-[72px_minmax(0,1fr)] items-baseline gap-2"
      >
        <dt class="truncate text-xs font-medium text-ink-gray-6">
          {{ row.label }}
        </dt>
        <dd
          class="min-w-0 break-words text-xs text-ink-gray-8"
          :class="{ 'font-mono tabular-nums': row.mono }"
          :title="row.value"
        >
          {{ row.value }}
        </dd>
      </div>
    </dl>

    <p
      v-if="errorCount"
      class="mb-3 flex items-center gap-1.5 text-xs text-danger"
    >
      <LucideTriangleAlert class="size-3.5 shrink-0" aria-hidden="true" />
      {{
        errorCount === 1
          ? __("1 recent error in the customer's browser")
          : __(
              "{0} recent errors in the customer's browser",
              String(errorCount)
            )
      }}
    </p>

    <template v-if="timelineLines.length">
      <button
        type="button"
        class="-mx-1 flex w-[calc(100%+0.5rem)] items-center justify-between gap-2 rounded px-1 text-xs font-medium text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
        :aria-expanded="timelineOpen"
        :aria-controls="timelineId"
        @click="timelineOpen = !timelineOpen"
      >
        <span>
          {{ __("Timeline") }}
          <span class="font-mono tabular-nums text-ink-gray-5">
            {{ timelineLines.length }}
          </span>
        </span>
        <LucideChevronRight
          class="size-4 transition-transform"
          :class="{ 'rotate-90': timelineOpen }"
          aria-hidden="true"
        />
      </button>
      <ol
        v-show="timelineOpen"
        :id="timelineId"
        class="mt-2 max-h-80 overflow-y-auto rounded-md border border-outline-gray-2 bg-surface-gray-1 px-2.5 py-2 font-mono text-2xs leading-5"
      >
        <li
          v-for="(line, index) in timelineLines"
          :key="index"
          class="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-1.5"
        >
          <span class="tabular-nums text-ink-gray-5">{{ line.at }}</span>
          <span
            class="break-words"
            :class="line.isError ? 'text-danger' : 'text-ink-gray-8'"
          >
            {{ line.text }}
          </span>
        </li>
      </ol>
    </template>

    <SessionReplayDialog
      v-if="replay.data.replay_url"
      v-model:open="playerOpen"
      :replay-url="replay.data.replay_url"
    />
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { useStorage } from "@vueuse/core";
import { Button, createResource } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideClapperboard from "~icons/lucide/clapperboard";
import LucidePlay from "~icons/lucide/play";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SessionReplayDialog from "./SessionReplayDialog.vue";

interface SessionDiagnostics {
  url?: string;
  route?: string[];
  title?: string;
  browser?: string | { name?: string; version?: string };
  os?: string | { name?: string; version?: string };
  viewport?: { w?: number; h?: number };
  versions?: Record<string, string>;
  recent_errors?: unknown[];
}

interface SessionReplayInfo {
  available: boolean;
  replay_url: string | null;
  diagnostics: SessionDiagnostics | null;
  summary: string;
  timeline: string;
}

interface DetailRow {
  label: string;
  value: string;
  mono: boolean;
}

const props = defineProps<{
  ticketId: string;
}>();

const headingId = `session-replay-${useId()}`;
const timelineId = `${headingId}-timeline`;
const playerOpen = ref(false);
const timelineOpen = useStorage("sessionReplayTimelineOpen", true);

const replay = createResource({
  url: "helpdesk.api.session_replay.get_session_replay",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: Boolean(props.ticketId),
});

watch(
  () => props.ticketId,
  (ticketId, previous) => {
    if (ticketId && ticketId !== previous) replay.reload();
  }
);

const diagnostics = computed<SessionDiagnostics | null>(
  () => (replay.data as SessionReplayInfo | undefined)?.diagnostics ?? null
);

function describe(value: SessionDiagnostics["browser"]): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  return [value.name, value.version].filter(Boolean).join(" ");
}

function pathOf(url?: string): string {
  if (!url) return "";
  try {
    return new URL(url, window.location.origin).pathname;
  } catch {
    return url;
  }
}

const details = computed<DetailRow[]>(() => {
  const d = diagnostics.value;
  if (!d) return [];
  const rows: DetailRow[] = [];

  const size =
    d.viewport?.w && d.viewport?.h ? `${d.viewport.w}×${d.viewport.h}` : "";
  const browser = [describe(d.browser), describe(d.os)]
    .filter(Boolean)
    .join(" · ");
  if (browser || size) {
    rows.push({
      label: __("Browser"),
      value: [browser, size].filter(Boolean).join(" · "),
      mono: false,
    });
  }

  const path =
    pathOf(d.url) || (d.route?.length ? `/app/${d.route.join("/")}` : "");
  if (path) rows.push({ label: __("Page"), value: path, mono: true });

  const versions = d.versions ?? {};
  const shown = ["erpnext", "frappe"].filter((app) => versions[app]);
  const apps = shown.length ? shown : Object.keys(versions).slice(0, 2);
  if (apps.length) {
    rows.push({
      label: __("Versions"),
      value: apps.map((app) => `${app} ${versions[app]}`).join(" · "),
      mono: true,
    });
  }
  return rows;
});

const errorCount = computed(
  () => diagnostics.value?.recent_errors?.length ?? 0
);

const ERROR_PREFIXES = ["server error:", "console error:", "request failed:"];

const timelineLines = computed(() => {
  const timeline =
    (replay.data as SessionReplayInfo | undefined)?.timeline ?? "";
  return timeline
    .split("\n")
    .filter(Boolean)
    .map((raw) => {
      const match = raw.match(/^(t\+\S+)\s(.*)$/);
      const text = match?.[2] ?? raw;
      return {
        at: match?.[1] ?? "",
        text,
        isError: ERROR_PREFIXES.some((prefix) => text.startsWith(prefix)),
      };
    });
});
</script>
