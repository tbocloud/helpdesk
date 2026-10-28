<template>
  <div class="flex flex-col gap-4">
    <SectionCard
      v-for="section in sections"
      :key="section.key"
      :title="section.title"
      :description="section.description"
      :count="data ? section.rows.length : undefined"
    >
      <ul v-if="section.rows.length" class="border-t border-outline-gray-1">
        <li
          v-for="r in section.rows"
          :key="r.name"
          class="border-b border-outline-gray-1 last:border-b-0"
        >
          <a
            :href="r.link"
            class="flex flex-col gap-1 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            <div class="flex flex-wrap items-center gap-1.5">
              <Badge
                :label="__(r.status)"
                :theme="THEME[r.status] || 'blue'"
                size="sm"
              />
              <Badge
                v-if="r.ci"
                :label="__('CI: {0}', r.ci)"
                :theme="r.ci === 'Failed' ? 'red' : 'gray'"
                size="sm"
              />
              <Badge
                v-if="r.check"
                :label="__('Check: {0}', r.check)"
                :theme="r.check === 'Failed' ? 'red' : 'gray'"
                size="sm"
              />
              <span class="font-mono text-sm text-ink-gray-6">{{ r.name }}</span>
            </div>
            <div class="truncate text-base text-ink-gray-9">
              {{ r.repository || r.source }}
              <template v-if="r.branch">({{ r.branch }})</template>
              <template v-if="r.ticket"> · #{{ r.ticket }}</template>
            </div>
            <div class="text-sm text-ink-gray-6">{{ details(r) }}</div>
            <div v-if="r.error" class="text-sm text-danger">{{ r.error }}</div>
          </a>
        </li>
      </ul>
      <p v-else-if="data" class="px-4 pb-4 text-sm text-ink-gray-5">
        {{ section.empty }}
      </p>
      <div
        v-else-if="releases.loading"
        class="mx-4 mb-4 h-16 animate-pulse rounded-lg bg-surface-gray-1"
      />
    </SectionCard>
    <ErrorMessage
      v-if="releases.error"
      :message="errorText(releases.error)"
    />
  </div>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Badge, createResource, ErrorMessage } from "frappe-ui";
import { computed } from "vue";
import { BOARD_API, useBoardRefresh } from "../boardMeta";

type Release = {
  name: string;
  status: string;
  source: string;
  repository: string;
  branch: string;
  ci: string;
  check: string;
  ticket: string;
  scheduled_for: string;
  assigned_name: string;
  decided_name: string;
  finished_at: string;
  error: string;
  sites: { site: string; status: string }[];
  apps: { app: string; from: string; to: string }[];
  link: string;
};

const THEME: Record<string, string> = {
  Succeeded: "green",
  Failed: "red",
  Rejected: "red",
  Cancelled: "gray",
  "Waiting for approval": "orange",
};

const releases = createResource({
  url: `${BOARD_API}.releases`,
  params: { days: 7 },
  auto: true,
});
useBoardRefresh(releases);
const data = computed(
  () =>
    releases.data as { pipeline: Release[]; finished: Release[] } | undefined
);

const sections = computed(() => [
  {
    key: "pipeline",
    title: __("In the pipeline"),
    description: __(
      "Every merge on its way to the customer sites: CI, the sandbox check, the approval, the deploy and the check after it."
    ),
    rows: data.value?.pipeline || [],
    empty: __("Nothing on its way."),
  },
  {
    key: "finished",
    title: __("Finished in the last 7 days"),
    description: "",
    rows: data.value?.finished || [],
    empty: __("Nothing finished this week."),
  },
]);

// what moves, where, and who decided, in one line
function details(r: Release): string {
  return [
    r.apps.map((a) => `${a.app} ${a.from || "?"} → ${a.to || "?"}`).join(", "),
    r.sites.map((s) => s.site).join(", "),
    r.scheduled_for ? __("scheduled {0}", r.scheduled_for) : "",
    r.decided_name
      ? __("decided by {0}", r.decided_name)
      : r.assigned_name
      ? __("waits for {0}", r.assigned_name)
      : "",
    r.finished_at ? __("finished {0}", r.finished_at) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
</script>
