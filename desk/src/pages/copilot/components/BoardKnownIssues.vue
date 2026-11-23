<template>
  <div class="flex flex-col gap-4">
    <div class="overflow-x-auto">
      <TabButtons
        v-model="status"
        size="sm"
        :aria-label="__('Known issue status')"
        :options="statuses"
      />
    </div>
    <SectionCard
      :title="__('What Copilot remembers')"
      :description="
        __(
          'Each error Copilot met, where it was seen, its fix and which sites have that fix. A fixed issue seen again on a site with the fix came back.'
        )
      "
      :count="issues.data ? rows.length : undefined"
    >
      <ul v-if="rows.length" class="border-t border-outline-gray-1">
        <li
          v-for="issue in rows"
          :key="issue.name"
          class="border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
        >
          <div class="flex flex-wrap items-center gap-1.5">
            <Badge
              :label="__(issue.status)"
              :theme="
                issue.status === 'Fixed'
                  ? 'green'
                  : issue.status === 'Open'
                  ? 'orange'
                  : 'gray'
              "
              size="sm"
            />
            <Badge
              v-if="issue.came_back"
              :label="__('Came back {0}x', String(issue.came_back))"
              theme="red"
              size="sm"
            />
            <Badge
              v-if="issue.missing_fix"
              :label="
                __('{0} sites without the fix', String(issue.missing_fix))
              "
              theme="red"
              size="sm"
            />
            <a
              :href="issue.link"
              class="font-mono text-sm text-ink-gray-6 underline-offset-2 hover:underline"
            >
              {{ issue.name }}
            </a>
          </div>
          <div class="mt-1 text-base text-ink-gray-9">{{ issue.title }}</div>
          <div class="text-sm text-ink-gray-6">
            {{
              [
                issue.app,
                issue.root_cause,
                __("first seen {0}", issue.first_seen),
                __("last seen {0}", issue.last_seen),
              ]
                .filter(Boolean)
                .join(" · ")
            }}
          </div>
          <div v-if="issue.fix" class="mt-1 text-sm text-ink-gray-7">
            {{ __("Fixed by") }}
            <a
              v-if="issue.fix.pull_request"
              :href="issue.fix.pull_request"
              target="_blank"
              rel="noopener"
              class="underline underline-offset-2"
            >
              {{ issue.fix.title || issue.fix.pull_request }}
            </a>
            <span v-else>{{ issue.fix.title || "-" }}</span>
            <span class="font-mono text-ink-gray-5">
              {{ issue.fix.merge_commit }}
            </span>
          </div>
          <ul class="mt-2 flex flex-col gap-1 text-sm">
            <li
              v-for="site in issue.sites"
              :key="site.site"
              class="flex flex-wrap items-center gap-x-2 text-ink-gray-7"
            >
              <span class="text-ink-gray-8">{{ site.site }}</span>
              <span class="text-ink-gray-5">{{ site.customer }}</span>
              <span>{{ __("{0} times", String(site.count)) }}</span>
              <span class="text-ink-gray-5">{{ site.last_seen }}</span>
              <a
                v-if="site.ticket"
                :href="`/helpdesk/tickets/${site.ticket}`"
                class="font-mono underline underline-offset-2"
              >
                #{{ site.ticket }}
              </a>
              <Badge
                v-if="site.has_fix"
                :label="
                  site.has_fix === 'Yes' ? __('has the fix') : __('no fix yet')
                "
                :theme="site.has_fix === 'Yes' ? 'green' : 'red'"
                size="sm"
              />
            </li>
          </ul>
        </li>
      </ul>
      <p v-else-if="issues.data" class="px-4 pb-4 text-sm text-ink-gray-5">
        {{ __("No known issues here.") }}
      </p>
      <div
        v-else-if="issues.loading"
        class="mx-4 mb-4 h-24 animate-pulse rounded-lg bg-surface-gray-1"
      />
      <ErrorMessage
        v-else-if="issues.error"
        class="px-4 pb-4"
        :message="errorText(issues.error)"
      />
    </SectionCard>
  </div>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Badge, createResource, ErrorMessage, TabButtons } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { BOARD_API, useBoardRefresh } from "../boardMeta";

type Issue = {
  name: string;
  title: string;
  status: string;
  app: string;
  root_cause: string;
  first_seen: string;
  last_seen: string;
  came_back: number;
  fix: {
    pull_request: string;
    title: string;
    merge_commit: string;
    fixed_at: string;
  } | null;
  sites: {
    site: string;
    customer: string;
    count: number;
    last_seen: string;
    ticket: string;
    has_fix: string;
  }[];
  missing_fix: number;
  link: string;
};

const statuses = [
  { label: __("All"), value: "" },
  { label: __("Open"), value: "Open" },
  { label: __("Fixed"), value: "Fixed" },
  { label: __("Not a bug"), value: "Not a bug" },
];
const status = ref("");
const issues = createResource({
  url: `${BOARD_API}.known_issues`,
  makeParams: () => ({ status: status.value || undefined }),
  auto: true,
});
watch(status, () => issues.reload());
useBoardRefresh(issues);
const rows = computed(() => (issues.data as Issue[] | undefined) || []);
</script>
