<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          size="md"
          :label="__('Refresh')"
          :loading="ads.loading && !!ads.data"
          @click="ads.reload()"
        >
          <template #icon
            ><LucideRefreshCw class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="relative flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pb-8 pt-4 md:px-8"
      >
        <TaskyState
          v-if="ads.error && !ads.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the ads')"
          :message="
            errorText(ads.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Retry')" @click="ads.reload()" />
        </TaskyState>

        <div
          v-else-if="!data"
          class="h-40 animate-pulse rounded-xl bg-surface-gray-3"
          aria-busy="true"
        />

        <template v-else>
          <div>
            <h2 class="mb-1 text-base font-semibold text-ink-gray-9">
              {{ __("Ads") }}
            </h2>
            <p class="max-w-prose text-p-sm text-ink-gray-6">
              {{
                __(
                  "Posts boosted with paid ads. To boost one, open it in the content calendar and press Boost this post."
                )
              }}
            </p>
          </div>

          <TaskyState
            v-if="data.blocked_reason"
            class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
            :icon="LucideMegaphone"
            :title="
              data.needs_reconnect
                ? __('Reconnect Meta to allow ads')
                : __('Ads aren\'t ready yet')
            "
            :message="data.blocked_reason"
          >
            <router-link :to="{ name: 'TaskyMeta', params: { projectId } }">
              <Button
                variant="solid"
                :label="
                  data.needs_reconnect
                    ? __('Reconnect Meta')
                    : __('Open the Meta tab')
                "
              />
            </router-link>
          </TaskyState>

          <template v-else>
            <section
              v-if="data.spend"
              class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-label="__('This month\'s spend')"
            >
              <div
                class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1"
              >
                <h3 class="text-base font-semibold text-ink-gray-9">
                  {{ __("This month") }}
                </h3>
                <p class="text-p-sm tabular-nums text-ink-gray-7">
                  {{
                    __(
                      "{0} planned of {1}",
                      formatMoney(data.spend.planned, data.spend.currency),
                      formatMoney(data.spend.cap, data.spend.currency)
                    )
                  }}
                </p>
              </div>
              <div
                class="mt-2 h-2 overflow-hidden rounded-full"
                :class="TRACK[meterTone]"
                role="meter"
                :aria-valuemin="0"
                :aria-valuemax="data.spend.cap"
                :aria-valuenow="Math.min(data.spend.planned, data.spend.cap)"
                :aria-label="__('Planned spend against this month\'s limit')"
              >
                <div
                  class="h-full rounded-full"
                  :class="FILL[meterTone]"
                  :style="{ width: `${percent}%` }"
                />
              </div>
              <p class="mt-2 text-p-sm text-ink-gray-6">
                {{
                  __(
                    "{0} is left. No boost can take the month past the limit.",
                    formatMoney(data.spend.left, data.spend.currency)
                  )
                }}
                <template v-if="data.account">
                  {{
                    __(
                      "Ad account: {0} ({1}).",
                      data.account.name || "",
                      data.account.currency || ""
                    )
                  }}
                </template>
              </p>
            </section>

            <TaskyState
              v-if="!data.boosts.length"
              class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
              :icon="LucideMegaphone"
              :title="__('No boosts yet')"
              :message="
                __(
                  'Open a published post in the content calendar and press Boost this post.'
                )
              "
            >
              <router-link :to="{ name: 'ContentCalendar' }">
                <Button :label="__('Open the content calendar')" />
              </router-link>
            </TaskyState>

            <ul v-else class="flex flex-col gap-4" role="list">
              <li
                v-for="b in data.boosts"
                :key="b.name"
                class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <ChannelIcon :channel="b.target" class="size-4 shrink-0" />
                  <span
                    class="min-w-0 flex-1 truncate text-base font-semibold text-ink-gray-9"
                  >
                    {{ b.post_title || b.post }}
                  </span>
                  <TaskyBadge
                    :tone="BOOST_STATUS[b.status].tone"
                    :icon="BOOST_STATUS[b.status].icon"
                    :label="__(BOOST_STATUS[b.status].label)"
                  />
                </div>
                <p class="text-p-sm text-ink-gray-6">
                  {{ __(b.goal) }} ·
                  {{ dayjs(b.start_date).format("D MMM") }}–{{
                    dayjs(b.end_date).format("D MMM YYYY")
                  }}
                  <template
                    v-if="
                      b.meta_status && ['Active', 'Paused'].includes(b.status)
                    "
                  >
                    · {{ __(b.meta_status) }}
                  </template>
                </p>
                <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
                  <div v-for="stat in stats(b)" :key="stat.label">
                    <dt class="text-xs text-ink-gray-6">{{ stat.label }}</dt>
                    <dd class="font-mono text-sm tabular-nums text-ink-gray-9">
                      {{ stat.value }}
                    </dd>
                  </div>
                </dl>
                <p
                  v-if="b.failure_reason"
                  role="alert"
                  class="flex items-start gap-2 text-p-sm text-danger"
                >
                  <LucideCircleAlert
                    class="mt-0.5 size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {{ b.failure_reason }}
                </p>
                <p v-if="b.rejection_note" class="text-p-sm text-ink-gray-6">
                  {{ b.rejection_note }}
                </p>
                <p
                  v-if="b.status === 'Pending approval'"
                  class="text-p-sm text-ink-gray-6"
                >
                  {{ __("Asked by {0}.", b.requested_by_name || "") }}
                </p>
                <BoostActions :boost="b" @changed="ads.reload()" />
              </li>
            </ul>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { FILL, TRACK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideMegaphone from "~icons/lucide/megaphone";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import {
  BOOST_STATUS,
  formatCount,
  formatMoney,
  type AdAccount,
  type Boost,
  type MonthSpend,
} from "../content/boost";
import BoostActions from "../content/components/BoostActions.vue";
import ChannelIcon from "../content/components/ChannelIcon.vue";
import ProjectNav from "./components/ProjectNav.vue";

interface AdsData {
  enabled: boolean;
  blocked_reason?: string | null;
  needs_reconnect: boolean;
  account?: AdAccount | null;
  spend?: MonthSpend | null;
  boosts: Boost[];
}

const props = defineProps<{ projectId: string }>();

const ads = createResource({
  url: "helpdesk.api.meta_ads.get_project_ads",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
});
const data = computed(() => ads.data as AdsData | undefined);

const percent = computed(() => {
  const s = data.value?.spend;
  return s && s.cap ? Math.min(100, Math.round((s.planned / s.cap) * 100)) : 0;
});
// colour only when the month is nearly (or fully) planned
const meterTone = computed<Tone>(() =>
  percent.value >= 100 ? "danger" : percent.value >= 80 ? "warning" : "neutral"
);

function stats(b: Boost) {
  return [
    { label: __("Budget"), value: formatMoney(b.total_budget, b.currency) },
    { label: __("Spent"), value: formatMoney(b.spend, b.currency) },
    { label: __("People reached"), value: formatCount(b.reach) },
    { label: __("Results"), value: formatCount(b.results) },
    {
      label: __("Cost per result"),
      value: b.results ? formatMoney(b.cost_per_result, b.currency) : "–",
    },
  ];
}
</script>
