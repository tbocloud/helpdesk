<template>
  <HomeCard :title="__('Systems')">
    <ul role="list">
      <li
        v-for="row in rows"
        :key="row.key"
        class="flex items-start justify-between gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
      >
        <span class="min-w-0">
          <span class="block break-words text-sm text-ink-gray-9">
            {{ row.label }}
          </span>
          <span
            v-if="row.detail"
            class="block truncate text-p-xs text-ink-gray-5"
            :title="row.detail"
          >
            {{ row.detail }}
          </span>
        </span>
        <TaskyBadge :tone="row.tone" :icon="TONE_ICON[row.tone]">
          {{ row.status }}
        </TaskyBadge>
      </li>
    </ul>
  </HomeCard>
</template>

<script setup lang="ts">
import TaskyBadge from "@/pages/tasky/components/TaskyBadge.vue";
import type { Tone } from "@/pages/tasky/taskMeta";
import { __ } from "@/translation";
import { computed, type Component } from "vue";
import LucideCircle from "~icons/lucide/circle";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideInfo from "~icons/lucide/info";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { Systems } from "../homeMeta";
import HomeCard from "./HomeCard.vue";

const props = defineProps<{ systems: Systems }>();

interface SystemRow {
  key: string;
  label: string;
  detail?: string;
  status: string;
  tone: Tone;
}

const TONE_ICON: Record<Tone, Component> = {
  neutral: LucideCircle,
  info: LucideInfo,
  warning: LucideTriangleAlert,
  success: LucideCircleCheck,
  danger: LucideCircleX,
};

const rows = computed<SystemRow[]>(() => {
  const s = props.systems;
  const result: SystemRow[] = s.connections.map((c) => ({
    key: `conn-${c.name}`,
    label: c.customer_name || c.name,
    detail:
      c.connection_status === "Connected"
        ? hostOf(c.site_url)
        : c.last_error || hostOf(c.site_url),
    status: __(c.connection_status || "Unknown"),
    tone:
      c.connection_status === "Connected"
        ? "success"
        : c.connection_status === "Error"
        ? "danger"
        : "neutral",
  }));
  for (const box of s.mailboxes) {
    result.push({
      key: `mail-${box.name}`,
      label: box.email_id,
      detail: box.no_failed
        ? __("{0} failed attempts", String(box.no_failed))
        : __("Email to tickets"),
      status: box.enable_incoming ? __("Receiving") : __("Paused"),
      tone: box.enable_incoming && !box.no_failed ? "success" : "warning",
    });
  }
  result.push({
    key: "teams",
    label: __("Notifications in {0}", s.teams.platform || __("chat")),
    status: s.teams.enabled ? __("On") : __("Off"),
    tone: s.teams.enabled ? "success" : "neutral",
  });
  result.push({
    key: "chat",
    label: __("TBO Chat"),
    detail: s.chat.enabled
      ? __("{0} open chats", String(s.chat.open))
      : undefined,
    status: s.chat.enabled ? __("On") : __("Off"),
    tone: s.chat.enabled ? "success" : "neutral",
  });
  result.push({
    key: "ai",
    label: __("AI triage"),
    detail: __("{0} AI calls today", String(s.ai.calls_today)),
    status: s.ai.triage_failed
      ? __("{0} failed", String(s.ai.triage_failed))
      : __("OK"),
    tone: s.ai.triage_failed ? "warning" : "success",
  });
  return result;
});

function hostOf(url: string | null) {
  if (!url) return undefined;
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
</script>
