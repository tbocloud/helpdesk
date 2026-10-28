<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="text-lg-medium text-ink-gray-9">
          {{ __("Copilot board") }}
        </h1>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="summary.loading"
          :aria-label="__('Refresh')"
          @click="summary.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "All of Copilot's work at a glance. Decide where you always do: open the ticket's Copilot dialog, the release, or the card in Teams."
            )
          }}
        </p>

        <!-- the top strip: the worker, runs waiting, the month's AI spend, shadow mode -->
        <p
          class="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-base text-ink-gray-8"
          aria-live="polite"
        >
          <template v-if="strip.length">
            <template v-for="(part, i) in strip" :key="part.key">
              <span v-if="i" class="text-ink-gray-4" aria-hidden="true">·</span>
              <span
                class="inline-flex items-center gap-1.5"
                :class="part.alert ? 'font-medium text-danger' : ''"
                :title="part.title"
              >
                <component
                  :is="part.icon"
                  class="size-4 shrink-0"
                  :class="part.alert ? '' : 'text-ink-gray-5'"
                  aria-hidden="true"
                />
                {{ part.text }}
              </span>
            </template>
          </template>
          <span
            v-else
            class="h-5 w-80 max-w-full animate-pulse rounded bg-surface-gray-2"
          />
        </p>

        <div class="mt-4 overflow-x-auto">
          <TabButtons
            :model-value="tab"
            size="md"
            :aria-label="__('Board view')"
            :options="tabs"
            @update:model-value="go($event)"
          />
        </div>

        <div class="mt-4">
          <BoardWork v-if="tab === 'work'" />
          <BoardApprovals v-else-if="tab === 'approvals'" />
          <BoardReleases v-else-if="tab === 'releases'" />
          <BoardSites v-else-if="tab === 'sites'" />
          <BoardKnownIssues v-else />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import { Button, createResource, TabButtons } from "frappe-ui";
import { computed, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideBot from "~icons/lucide/bot";
import LucideCircleDollarSign from "~icons/lucide/circle-dollar-sign";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideScanSearch from "~icons/lucide/scan-search";
import { BOARD_API, useBoardRefresh } from "./boardMeta";
import BoardApprovals from "./components/BoardApprovals.vue";
import BoardKnownIssues from "./components/BoardKnownIssues.vue";
import BoardReleases from "./components/BoardReleases.vue";
import BoardSites from "./components/BoardSites.vue";
import BoardWork from "./components/BoardWork.vue";

type Summary = {
  enabled: boolean;
  shadow_mode: boolean;
  watch_enabled: boolean;
  queued: number;
  waiting_for_a_worker: number;
  is_manager: boolean;
  workers?: {
    worker: string;
    last_seen: string;
    minutes_ago: number;
    online: boolean;
  }[];
  month_spend_usd?: number;
  month_budget_usd?: number;
};

const TABS = ["work", "approvals", "releases", "sites", "issues"] as const;
type Tab = (typeof TABS)[number];

const route = useRoute();
const router = useRouter();
const tab = computed<Tab>(() =>
  TABS.includes(route.query.tab as Tab) ? (route.query.tab as Tab) : "work"
);
const tabs = [
  { label: __("Work"), value: "work" },
  { label: __("Approvals"), value: "approvals" },
  { label: __("Releases"), value: "releases" },
  { label: __("Sites"), value: "sites" },
  { label: __("Known issues"), value: "issues" },
];
function go(value: string) {
  router.replace({
    query: { ...route.query, tab: value === "work" ? undefined : value },
  });
}

const summary = createResource({
  url: `${BOARD_API}.summary`,
  auto: true,
});
useBoardRefresh(summary);

const strip = computed(() => {
  const s = summary.data as Summary | undefined;
  if (!s) return [];
  const parts: {
    key: string;
    icon: Component;
    text: string;
    alert?: boolean;
    title?: string;
  }[] = [];
  if (!s.enabled) {
    parts.push({
      key: "off",
      icon: LucideBot,
      text: __("Copilot is switched off"),
      alert: true,
    });
  }
  if (s.workers) {
    const online = s.workers.filter((w) => w.online);
    const last = s.workers[0];
    parts.push({
      key: "worker",
      icon: LucideBot,
      text: online.length
        ? __("Worker online")
        : last
        ? __("Worker not seen for {0} min", String(Math.round(last.minutes_ago)))
        : __("No worker has asked for work"),
      alert: !online.length,
      title: s.workers
        .map((w) => `${w.worker}: ${w.last_seen}`)
        .join("\n"),
    });
  }
  parts.push({
    key: "waiting",
    icon: LucideHourglass,
    text: s.waiting_for_a_worker
      ? __("{0} waiting for a worker", String(s.waiting_for_a_worker))
      : __("{0} queued", String(s.queued)),
    alert: s.waiting_for_a_worker > 0,
  });
  if (s.month_spend_usd !== undefined) {
    const budget = s.month_budget_usd || 0;
    parts.push({
      key: "spend",
      icon: LucideCircleDollarSign,
      text: budget
        ? __(
            "${0} of ${1} this month",
            s.month_spend_usd.toFixed(2),
            budget.toFixed(0)
          )
        : __("${0} this month", s.month_spend_usd.toFixed(2)),
      alert: !!budget && s.month_spend_usd >= budget * 0.8,
    });
  }
  if (s.shadow_mode) {
    parts.push({
      key: "shadow",
      icon: LucideEyeOff,
      text: __("Shadow mode: customers see nothing from Copilot"),
    });
  }
  parts.push({
    key: "watch",
    icon: LucideScanSearch,
    text: s.watch_enabled ? __("Error watch on") : __("Error watch off"),
  });
  return parts;
});
</script>
