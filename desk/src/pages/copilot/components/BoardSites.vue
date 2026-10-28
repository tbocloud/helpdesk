<template>
  <div class="flex flex-col gap-4">
    <div class="sm:w-72">
      <Link
        v-model="customer"
        doctype="HD Customer"
        :label="__('Customer')"
        :placeholder="__('Every customer')"
      />
    </div>
    <div
      v-if="rows.length"
      class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"
    >
      <SectionCard
        v-for="site in rows"
        :key="site.name"
        :title="site.site"
        :description="`${site.customer} · ${site.environment} · ${__(
          'Copilot level: {0}',
          site.level
        )}`"
      >
        <template #actions>
          <a
            :href="site.link"
            class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ __("Site card") }}
          </a>
        </template>
        <div class="flex flex-col gap-3 px-4 pb-4 text-sm">
          <div>
            <div class="text-ink-gray-5">
              {{
                site.apps_read_at
                  ? __("Apps, read {0}", site.apps_read_at)
                  : __("Apps")
              }}
            </div>
            <ul class="mt-1 flex flex-col gap-1">
              <li
                v-for="app in site.apps"
                :key="app.app"
                class="flex items-center justify-between gap-2"
              >
                <span class="truncate text-ink-gray-8">
                  {{ app.app }}
                  <span class="text-ink-gray-5">{{ app.branch }}</span>
                </span>
                <span class="flex shrink-0 items-center gap-1.5">
                  <span class="font-mono text-ink-gray-6">{{ app.commit || "-" }}</span>
                  <Badge
                    :label="__(app.drift)"
                    :theme="
                      app.drift === 'Drift'
                        ? 'red'
                        : app.drift === 'In sync'
                        ? 'green'
                        : 'gray'
                    "
                    size="sm"
                  />
                </span>
              </li>
              <li v-if="!site.apps.length" class="text-ink-gray-5">
                {{ __("No apps on the card") }}
              </li>
            </ul>
          </div>
          <div>
            <div class="text-ink-gray-5">{{ __("Error watch") }}</div>
            <div class="mt-1 text-ink-gray-8">
              <template v-if="site.watch.on">
                {{
                  site.watch.checked_at
                    ? __("checked {0}", site.watch.checked_at)
                    : __("not checked yet")
                }}
                <span v-if="site.watch.failures" class="text-danger">
                  · {{ __("{0} checks failed", String(site.watch.failures)) }}
                </span>
              </template>
              <template v-else>{{ __("off for this customer") }}</template>
            </div>
            <div v-if="site.watch.note" class="mt-1 text-danger">
              {{ site.watch.note }}
            </div>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              :label="__('{0} open known issues', String(site.open_issues))"
              :theme="site.open_issues ? 'orange' : 'gray'"
              size="sm"
            />
            <Badge
              v-if="site.missing_fixes"
              :label="__('{0} fixes not here yet', String(site.missing_fixes))"
              theme="red"
              size="sm"
            />
            <Badge
              v-if="!site.connected"
              :label="__('No connection')"
              theme="red"
              size="sm"
            />
          </div>
        </div>
      </SectionCard>
    </div>
    <p v-else-if="sites.data" class="text-sm text-ink-gray-5">
      {{ __("No site cards.") }}
    </p>
    <div
      v-else-if="sites.loading"
      class="h-40 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
    />
    <ErrorMessage v-else-if="sites.error" :message="errorText(sites.error)" />
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Badge, createResource, ErrorMessage } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { BOARD_API, useBoardRefresh } from "../boardMeta";

type Site = {
  name: string;
  customer: string;
  environment: string;
  site: string;
  connected: boolean;
  level: string;
  apps_read_at: string;
  apps: { app: string; branch: string; commit: string; drift: string }[];
  watch: { on: boolean; checked_at: string; failures: number; note: string };
  open_issues: number;
  missing_fixes: number;
  link: string;
};

const customer = ref("");
const sites = createResource({
  url: `${BOARD_API}.sites`,
  makeParams: () => ({ customer: customer.value || undefined }),
  auto: true,
});
watch(customer, () => sites.reload());
useBoardRefresh(sites);
const rows = computed(() => (sites.data as Site[] | undefined) || []);
</script>
