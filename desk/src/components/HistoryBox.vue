<template>
  <div class="text-center text-sm text-ink-gray-5">
    <template v-if="relatedActivities.length > 1">
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded font-medium text-ink-gray-7 hover:text-ink-gray-9"
        :aria-expanded="show_others"
        @click="show_others = !show_others"
      >
        {{ groupLabel }}
        <SelectIcon aria-hidden="true" />
      </button>
      <Tooltip :text="dateFormat(creation, dateTooltipFormat)">
        <span class="ms-2 font-mono tabular-nums">{{ timeAgo(creation) }}</span>
      </Tooltip>
    </template>
    <template v-else>
      <span class="font-medium text-ink-gray-7">{{ user }}</span>
      {{ content }}
      <Tooltip :text="dateFormat(creation, dateTooltipFormat)">
        <span class="ms-1 font-mono tabular-nums"
          >· {{ timeAgo(creation) }}</span
        >
      </Tooltip>
    </template>
    <ul v-if="show_others" class="mt-1 space-y-1">
      <li
        v-for="relatedActivity in relatedActivities"
        :key="relatedActivity.creation"
      >
        <span class="font-medium text-ink-gray-7">{{
          relatedActivity.user
        }}</span>
        {{ relatedActivity.content }}
        <Tooltip
          :text="dateFormat(relatedActivity.creation, dateTooltipFormat)"
        >
          <span class="ms-1 font-mono tabular-nums">
            · {{ timeAgo(relatedActivity.creation) }}
          </span>
        </Tooltip>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { SelectIcon } from "@/components/icons";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { __ } from "@/translation";
import { computed, ref } from "vue";
const props = defineProps({
  activity: {
    type: Object,
    required: true,
  },
});

const { user, content, creation } = props.activity;
const relatedActivities = computed(() => props.activity.relatedActivities);

let show_others = ref(false);

const groupLabel = computed(() =>
  __(
    show_others.value
      ? "Hide {0} changes from {1}"
      : "Show {0} changes from {1}",
    [String(relatedActivities.value.length), user]
  )
);
</script>
