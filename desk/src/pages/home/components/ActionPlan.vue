<template>
  <!-- nothing open means nothing to plan; the header already says "All clear" -->
  <SectionCard
    v-if="!(data && !data.steps.length)"
    :title="__('Your action plan')"
    :description="description"
    :icon="LucideListOrdered"
  >
    <template v-if="data?.ai_enabled" #actions>
      <Button
        size="sm"
        variant="ghost"
        :label="__('Refresh plan')"
        :icon-left="LucideRefreshCw"
        :loading="refreshPlan.loading"
        @click="refreshPlan.submit({ refresh: true })"
      />
    </template>

    <div
      v-if="!data && !plan.error"
      class="flex flex-col gap-3 px-4 py-4"
      role="status"
      :aria-label="__('Loading your plan')"
    >
      <span
        v-for="width in ['w-11/12', 'w-4/5', 'w-2/3']"
        :key="width"
        class="h-4 animate-pulse rounded bg-surface-gray-2"
        :class="width"
      />
    </div>

    <div
      v-else-if="!data"
      class="flex flex-wrap items-center gap-3 px-4 py-4 text-p-sm text-ink-gray-6"
      role="alert"
    >
      <LucideCircleAlert
        class="size-4 shrink-0 text-danger"
        aria-hidden="true"
      />
      {{ __("Couldn't load your plan.") }}
      <Button size="sm" :label="__('Retry')" @click="plan.reload()" />
    </div>

    <template v-else>
      <p
        v-if="data.stale"
        class="flex items-start gap-2 border-b border-outline-gray-2 px-4 py-2 text-p-sm text-ink-gray-6"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{
          __(
            "Your work changed since this plan was written. Refresh it to catch up."
          )
        }}
      </p>
      <ol class="flex flex-col gap-3 px-4 py-4" role="list">
        <li
          v-for="(step, index) in data.steps"
          :key="index"
          class="flex items-start gap-3"
        >
          <span
            class="mt-px w-5 shrink-0 text-right font-mono text-sm tabular-nums text-ink-gray-5"
            aria-hidden="true"
            >{{ index + 1 }}.</span
          >
          <RouterLink
            v-if="step.task && step.project"
            :to="{ name: 'TaskyProject', params: { projectId: step.project } }"
            class="min-w-0 break-words rounded-sm text-p-base text-ink-gray-9 underline decoration-outline-gray-3 underline-offset-2 hover:decoration-ink-gray-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ step.text }}
          </RouterLink>
          <span v-else class="min-w-0 break-words text-p-base text-ink-gray-9">
            {{ step.text }}
          </span>
        </li>
      </ol>
    </template>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, toast } from "frappe-ui";
import { computed, watch } from "vue";
import { RouterLink } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideListOrdered from "~icons/lucide/list-ordered";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import type { ActionPlan, YourDay } from "../homeMeta";

const props = defineProps<{
  /** Home's day; a new one (after a reload) means the plan may have gone stale. */
  day: YourDay;
}>();

// its own request after Home has loaded, so a slow AI never holds the page up
const plan = createResource({
  url: "helpdesk.api.home.get_action_plan",
  auto: true,
});

const refreshPlan = createResource({
  url: "helpdesk.api.home.get_action_plan",
  onSuccess(data: ActionPlan) {
    plan.setData(data);
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't refresh your plan.")));
  },
});

const data = computed<ActionPlan | null>(() => plan.data ?? null);

watch(
  () => props.day,
  () => plan.reload()
);

const description = computed(() => {
  const p = data.value;
  if (!p) return undefined;
  if (p.source === "ai") {
    return p.generated_at
      ? __(
          "Written by AI from your open work, {0}.",
          dayjs(p.generated_at).fromNow()
        )
      : __("Written by AI from your open work.");
  }
  const built = __("Built from your open work, most urgent first.");
  return p.reason ? `${built} ${p.reason}` : built;
});
</script>
