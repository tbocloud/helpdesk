<template>
  <SectionCard
    :title="__('Analysis')"
    :icon="LucideChartColumn"
    :description="
      __('Written by AI from the numbers on this page; it never adds its own.')
    "
  >
    <template v-if="canRefresh" #actions>
      <Button
        size="sm"
        :loading="refresh.loading"
        :label="analysis?.current ? __('Refresh') : __('Write analysis')"
        @click="refresh.submit({ period, department })"
      >
        <template #prefix>
          <LucideSparkles class="size-3.5" aria-hidden="true" />
        </template>
      </Button>
    </template>

    <div class="flex flex-col gap-3 px-4 py-3">
      <p
        v-if="refresh.error"
        class="flex items-start gap-1.5 text-p-sm text-danger"
        role="alert"
      >
        <LucideCircleAlert
          class="mt-0.5 size-3.5 shrink-0"
          aria-hidden="true"
        />
        {{ errorText(refresh.error, __("Couldn't write the analysis.")) }}
      </p>

      <template v-if="shown?.status === 'ready'">
        <p v-if="!shown.current" class="text-xs text-ink-gray-5">
          {{ __("From {0}", rangeText(shown.period_start!, shown.period_end!)) }}
        </p>
        <p class="text-p-sm text-ink-gray-8">{{ shown.summary }}</p>
        <div v-if="shown.risks?.length">
          <h3 class="flex items-center gap-1.5 text-sm-medium text-ink-gray-8">
            <LucideTriangleAlert
              class="size-4 shrink-0 text-danger"
              aria-hidden="true"
            />
            {{ __("Risks") }}
          </h3>
          <ul class="mt-1.5 flex list-disc flex-col gap-1 pl-6">
            <li
              v-for="item in shown.risks"
              :key="item"
              class="text-p-sm text-ink-gray-7"
            >
              {{ item }}
            </li>
          </ul>
        </div>
        <div v-if="shown.needs_help?.length">
          <h3 class="flex items-center gap-1.5 text-sm-medium text-ink-gray-8">
            <LucideUser
              class="size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            {{ __("Who could use help") }}
          </h3>
          <ul class="mt-1.5 flex list-disc flex-col gap-1 pl-6">
            <li
              v-for="item in shown.needs_help"
              :key="item"
              class="text-p-sm text-ink-gray-7"
            >
              {{ item }}
            </li>
          </ul>
        </div>
      </template>

      <p
        v-else-if="shown?.status === 'unavailable'"
        class="text-p-sm text-ink-gray-6"
      >
        {{ shown.reason }}
        {{ __("The scores and champions don't depend on it.") }}
      </p>

      <p v-else class="text-p-sm text-ink-gray-6">
        {{
          canRefresh
            ? __(
                "No analysis yet. It's written when a period closes, or now with Write analysis."
              )
            : __("No analysis yet. It's written when a period closes.")
        }}
      </p>
    </div>
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUser from "~icons/lucide/user";
import { rangeText, type Analysis } from "../teamDashboardMeta";

const props = defineProps<{
  analysis: Analysis | null;
  period: string;
  department: string | null;
  /** System and Agent Managers */
  canRefresh: boolean;
}>();

// a refreshed analysis replaces the loaded one until the page loads another
const fresh = ref<Analysis | null>(null);
watch(
  () => props.analysis,
  () => (fresh.value = null)
);
const shown = computed(() => fresh.value || props.analysis);

const refresh = createResource({
  url: "helpdesk.api.team_dashboard.refresh_analysis",
  onSuccess(data: Analysis) {
    fresh.value = data;
  },
});
</script>
