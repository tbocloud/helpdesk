<template>
  <section
    class="flex flex-col gap-3 border-t border-outline-gray-2 pt-4"
    :aria-label="__('Boost')"
  >
    <h4 class="text-base-medium text-ink-gray-9">{{ __("Boost") }}</h4>

    <div
      v-if="state.loading && !data"
      class="h-16 animate-pulse rounded-lg bg-surface-gray-1"
      aria-busy="true"
    />
    <p
      v-else-if="state.error && !data"
      role="alert"
      class="flex flex-wrap items-center gap-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      {{ errorText(state.error, __("Couldn't load the boost details.")) }}
      <Button
        variant="ghost"
        :label="__('Try again')"
        @click="state.reload()"
      />
    </p>

    <template v-else-if="data">
      <p
        v-if="data.not_published"
        class="flex items-start gap-2 text-p-sm text-ink-gray-7"
        role="note"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ data.not_published }}
      </p>
      <p
        v-else-if="data.blocked_reason"
        class="flex items-start gap-2 text-p-sm text-ink-gray-7"
        role="note"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          {{ data.blocked_reason }}
          <router-link
            v-if="data.project"
            :to="{ name: 'TaskyMeta', params: { projectId: data.project } }"
            class="rounded font-medium text-brand-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          >
            {{
              data.needs_reconnect
                ? __("Reconnect Meta")
                : __("Open the Meta tab")
            }}
          </router-link>
        </span>
      </p>

      <ul v-if="data.boosts.length" class="flex flex-col gap-2" role="list">
        <li
          v-for="b in data.boosts"
          :key="b.name"
          class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 px-3 py-2"
        >
          <div class="flex flex-wrap items-center gap-2">
            <ChannelIcon :channel="b.target" class="size-4 shrink-0" />
            <span class="text-sm-medium text-ink-gray-9">{{ __(b.goal) }}</span>
            <TaskyBadge
              :tone="BOOST_STATUS[b.status].tone"
              :icon="BOOST_STATUS[b.status].icon"
              :label="__(BOOST_STATUS[b.status].label)"
            />
          </div>
          <p class="text-p-sm tabular-nums text-ink-gray-7">
            {{ formatMoney(b.total_budget, b.currency) }} ·
            {{ dayjs(b.start_date).format("D MMM") }}–{{
              dayjs(b.end_date).format("D MMM")
            }}
            <template v-if="b.status !== 'Pending approval'">
              · {{ __("spent {0}", formatMoney(b.spend, b.currency)) }} ·
              {{ __("{0} reached", formatCount(b.reach)) }}
            </template>
          </p>
          <p
            v-if="b.meta_status && ['Active', 'Paused'].includes(b.status)"
            class="text-p-sm text-ink-gray-6"
          >
            {{ __(b.meta_status) }}
          </p>
          <p v-if="b.failure_reason" role="alert" class="text-p-sm text-danger">
            {{ b.failure_reason }}
          </p>
          <p v-if="b.rejection_note" class="text-p-sm text-ink-gray-6">
            {{ b.rejection_note }}
          </p>
          <p
            v-if="b.status === 'Pending approval' && !data.can_spend"
            class="text-p-sm text-ink-gray-6"
          >
            {{ __("Waiting for the Digital Marketing Head.") }}
          </p>
          <BoostActions :boost="b" @changed="changed" />
        </li>
      </ul>

      <div
        v-if="data.can_spend || data.targets.length"
        class="flex flex-wrap items-center justify-between gap-2"
      >
        <p v-if="data.spend" class="text-p-sm tabular-nums text-ink-gray-6">
          {{
            __(
              "This month: {0} of {1} planned",
              formatMoney(data.spend.planned, data.spend.currency),
              formatMoney(data.spend.cap, data.spend.currency)
            )
          }}
        </p>
        <Button
          class="ms-auto"
          variant="solid"
          :label="__('Boost this post')"
          :disabled="!canBoost"
          @click="showDialog = true"
        >
          <template #prefix>
            <LucideRocket class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>

    <BoostDialog
      v-if="data?.account && post"
      v-model="showDialog"
      :post="post.name"
      :targets="data.targets"
      :goals="data.goals"
      :currency="data.account.currency || 'INR'"
      :can-spend="data.can_spend"
      @done="changed"
    />
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideRocket from "~icons/lucide/rocket";
import {
  BOOST_STATUS,
  formatCount,
  formatMoney,
  type AdAccount,
  type Boost,
  type MonthSpend,
} from "../boost";
import type { ContentPost } from "../constants";
import BoostActions from "./BoostActions.vue";
import BoostDialog from "./BoostDialog.vue";
import ChannelIcon from "./ChannelIcon.vue";

interface BoostState {
  project?: string | null;
  can_spend: boolean;
  blocked_reason?: string | null;
  needs_reconnect: boolean;
  not_published?: string | null;
  targets: string[];
  account?: AdAccount | null;
  spend?: MonthSpend | null;
  boosts: Boost[];
  goals: string[];
}

const props = defineProps<{ post: ContentPost | null; open: boolean }>();
const emit = defineEmits<{ (e: "changed"): void }>();

const showDialog = ref(false);
const state = createResource({
  url: "helpdesk.api.meta_ads.get_boost_state",
  makeParams: () => ({ post: props.post?.name }),
});
const data = computed(() => state.data as BoostState | undefined);
const canBoost = computed(
  () => !!data.value && !data.value.blocked_reason && !data.value.not_published
);

watch(
  () => [props.open, props.post?.name],
  ([isOpen]) => {
    if (isOpen && props.post) state.reload();
  },
  { immediate: true }
);

async function changed() {
  await state.reload();
  emit("changed");
}
</script>
