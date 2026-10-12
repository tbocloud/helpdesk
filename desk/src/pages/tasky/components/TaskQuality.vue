<template>
  <!-- the task's weight and quality on the Scoreboard (team_dashboard.task_weight / task_quality) -->
  <section
    class="flex flex-col gap-2 rounded-md border border-outline-gray-2 px-3 py-2.5"
    :aria-labelledby="`quality-${task}`"
  >
    <h3 :id="`quality-${task}`" class="text-xs text-ink-gray-5">
      {{ __("On the Scoreboard") }}
    </h3>
    <p class="flex items-start gap-2 text-p-sm text-ink-gray-8">
      <LucideWeight
        class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <span>
        <span class="font-medium tabular-nums">{{
          __("Weight {0}", num(info.weight))
        }}</span>
        <template v-if="info.weight_reasons.length">
          — {{ info.weight_reasons.join(", ") }}</template
        >
      </span>
    </p>
    <p class="flex items-start gap-2 text-p-sm text-ink-gray-8">
      <LucideBadgeCheck
        class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      <span>
        <span class="font-medium tabular-nums">{{
          __("Quality ×{0}", num(info.quality))
        }}</span>
        — {{ info.quality_reasons.join(", ") }}
        <template v-if="info.rated_by_name">
          · {{ __("rated by {0}", info.rated_by_name) }}</template
        >
      </span>
    </p>

    <div
      v-if="info.can_rate"
      class="flex flex-col gap-1.5 border-t border-outline-gray-1 pt-2"
    >
      <span :id="`rate-${task}`" class="text-xs text-ink-gray-6">
        {{
          reviewing
            ? __("Rate the work (optional, saved when you approve)")
            : __("Rate the work (optional)")
        }}
      </span>
      <div class="flex flex-wrap items-center gap-2">
        <TabButtons
          :model-value="current"
          :options="RATINGS.map((r) => ({ label: __(r), value: r }))"
          :aria-labelledby="`rate-${task}`"
          :class="rate.loading ? 'pointer-events-none opacity-60' : ''"
          @update:model-value="choose"
        />
        <Button
          v-if="current"
          variant="ghost"
          :label="__('Clear rating')"
          :loading="rate.loading && clearing"
          @click="choose('')"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, TabButtons, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideBadgeCheck from "~icons/lucide/badge-check";
import LucideWeight from "~icons/lucide/weight";

/** What get_task_detail and rate_task return as `quality`. */
export interface TaskQualityInfo {
  weight: number;
  weight_reasons: string[];
  quality: number;
  quality_reasons: string[];
  rating: string | null;
  rated_by: string | null;
  rated_by_name: string | null;
  rated_on: string | null;
  can_rate: boolean;
}

// helpdesk.team_dashboard.RATINGS, worst to best
const RATINGS = ["Needs rework", "Good", "Excellent"];

const props = defineProps<{
  task: string;
  quality: TaskQualityInfo;
  /** Waiting for review: the rating goes with Approve instead of saving now. */
  reviewing?: boolean;
}>();
/** The rating picked for Approve, while the task waits for review. */
const pending = defineModel<string>("pending", { default: "" });
const emit = defineEmits<{ rated: [] }>();

const info = ref<TaskQualityInfo>(props.quality);
watch(
  () => props.quality,
  (q) => (info.value = q)
);
const current = computed(() =>
  props.reviewing ? pending.value : info.value.rating || ""
);

const clearing = ref(false);
const rate = createResource({
  url: "helpdesk.tasky.api.rate_task",
  onSuccess(data: TaskQualityInfo) {
    info.value = data;
    toast.success(
      data.rating ? __("Rated {0}", __(data.rating)) : __("Rating cleared")
    );
    emit("rated");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save the rating. Try again.")));
  },
});

function choose(rating: string) {
  if (props.reviewing) {
    pending.value = rating;
    return;
  }
  if (rate.loading || rating === (info.value.rating || "")) return;
  clearing.value = !rating;
  rate.submit({ task: props.task, rating: rating || null });
}

function num(value: number) {
  return String(Math.round(value * 100) / 100);
}
</script>
