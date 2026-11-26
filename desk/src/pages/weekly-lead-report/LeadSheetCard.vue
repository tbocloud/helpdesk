<template>
  <!-- the KSA lead report's fields on the Lead page; Edit lead changes them
       (docs/weekly-lead-report.md) -->
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    aria-labelledby="lead-sheet-title"
  >
    <div
      class="flex items-center gap-2 border-b border-outline-gray-2 px-4 py-3"
    >
      <h2 id="lead-sheet-title" class="text-base-medium text-ink-gray-9">
        {{ __("Lead report") }}
      </h2>
      <router-link
        :to="{ name: 'LeadReport' }"
        class="ml-auto rounded text-p-sm text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      >
        {{ __("Open report") }}
      </router-link>
    </div>

    <TaskyState
      v-if="sheet.error"
      class="py-6"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load these fields')"
      :message="errorText(sheet.error, __('Try again in a minute.'))"
    >
      <Button :label="__('Try again')" @click="sheet.reload()" />
    </TaskyState>
    <div
      v-else-if="!data"
      class="flex flex-col gap-2 p-4"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div
        v-for="n in 4"
        :key="n"
        class="h-5 animate-pulse rounded bg-surface-gray-1"
      />
    </div>
    <dl
      v-else
      class="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 px-4 py-3 text-sm"
    >
      <template v-for="field in fields" :key="field.label">
        <dt class="text-ink-gray-6">{{ field.label }}</dt>
        <dd
          class="min-w-0 whitespace-pre-line break-words"
          :class="field.value ? 'text-ink-gray-8' : 'text-ink-gray-6'"
        >
          {{ field.value || __("Not set") }}
        </dd>
      </template>
    </dl>
  </section>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource } from "frappe-ui";
import { computed, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { WEEKLY_API, type WeekRow } from "./weeklyLeadReport";

const props = defineProps<{ leadId: string }>();

const sheet = createResource({
  url: `${WEEKLY_API}.get_lead_sheet`,
  makeParams: () => ({ lead: props.leadId }),
  auto: true,
});
const data = computed(() => sheet.data as WeekRow | undefined);
// the Lead page reloads it after the Edit lead dialog saves
defineExpose({ reload: () => sheet.reload() });

watch(
  () => props.leadId,
  () => sheet.reload()
);

const fields = computed(() => {
  const d = data.value!;
  return [
    { label: __("Designation"), value: d.designation },
    { label: __("Requirement"), value: d.requirement_label },
    {
      label: __("Conversion possibility"),
      value: d.conversion && __(d.conversion),
    },
    { label: __("Visits this week"), value: d.visits ? String(d.visits) : "" },
    { label: __("Follow-up plan"), value: d.follow_up && __(d.follow_up) },
    { label: __("Remarks"), value: d.remarks },
  ];
});
</script>
