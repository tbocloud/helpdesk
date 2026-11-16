<template>
  <!-- what the sidebar's "Needs your attention" card counts, as a list: the most pressing
       first, a short list until the person asks for all of it (docs/follow-ups.md) -->
  <SectionCard
    v-if="attention.error && !attention.data"
    :title="__('Needs your attention')"
    :icon="LucideBellRing"
  >
    <p
      class="flex flex-wrap items-center gap-3 px-4 py-4 text-p-sm text-ink-gray-7"
    >
      {{ __("Couldn't load what is waiting on you.") }}
      <Button :label="__('Retry')" @click="attention.reload()" />
    </p>
  </SectionCard>
  <SectionCard
    v-else-if="total"
    :title="__('Needs your attention')"
    :count="total"
    :icon="LucideBellRing"
    :description="
      __('Most urgent first. Open an item to act on it, or to see who has it.')
    "
  >
    <template v-if="total > SHORT_LIST" #actions>
      <Button
        :label="showAll ? __('Show fewer') : __('Show all {0}', String(total))"
        :loading="attention.loading"
        :aria-expanded="showAll"
        @click="showAll = !showAll"
      />
    </template>
    <FollowUpList :rows="rows" empty="" />
  </SectionCard>
</template>

<script setup lang="ts">
import type { FollowUpRow } from "@/components/followUps";
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideBellRing from "~icons/lucide/bell-ring";
import FollowUpList from "./FollowUpList.vue";

// enough to start the day with; the rest is one press away
const SHORT_LIST = 10;

const showAll = ref(false);
const attention = createResource({
  url: "helpdesk.api.follow_ups.get_my_follow_ups",
  makeParams: () => ({ limit: showAll.value ? undefined : SHORT_LIST }),
  auto: true,
});
watch(showAll, () => attention.reload());

const total = computed<number>(() => attention.data?.total ?? 0);
const rows = computed<FollowUpRow[]>(() => attention.data?.rows ?? []);

defineExpose({ reload: () => attention.reload() });
</script>
