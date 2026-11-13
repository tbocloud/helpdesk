<template>
  <SettingsSection
    :title="__('History')"
    :description="__('Who changed this and what, newest first.')"
  >
    <p v-if="history.error" class="text-p-sm text-ink-gray-6">
      {{ errorText(history.error, __("Couldn't load the history.")) }}
      <Button
        variant="ghost"
        :label="__('Try again')"
        @click="history.reload()"
      />
    </p>
    <div
      v-else-if="!history.data"
      class="h-12 animate-pulse rounded-lg bg-surface-gray-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    />
    <ol v-else class="flex flex-col gap-3">
      <li
        v-for="(change, i) in shown"
        :key="i"
        class="flex flex-col gap-0.5 border-l-2 border-outline-gray-2 pl-3"
      >
        <span class="text-p-sm text-ink-gray-8">
          {{
            __("{0}, {1}", [
              change.by,
              dayjs(change.at).format("D MMM YYYY, h:mm a"),
            ])
          }}
        </span>
        <ul class="text-p-xs text-ink-gray-6">
          <li v-for="(line, j) in change.lines" :key="j" class="break-words">
            {{ line }}
          </li>
        </ul>
      </li>
      <li
        class="border-l-2 border-outline-gray-2 pl-3 text-p-sm text-ink-gray-6"
      >
        {{
          __("Created by {0}, {1}", [
            history.data.created_by,
            dayjs(history.data.created_on).format("D MMM YYYY"),
          ])
        }}
      </li>
      <li v-if="history.data.changes.length > shown.length">
        <Button
          variant="ghost"
          :label="__('Show all {0} changes', [history.data.changes.length])"
          @click="all = true"
        />
      </li>
    </ol>
  </SettingsSection>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, ref, watch } from "vue";
import SettingsSection from "../SettingsSection.vue";

const props = defineProps<{
  doctype: string;
  name: string;
  /** changes when the record is saved, so the list catches up */
  version?: string;
}>();

const SHOWN = 5;

const history = createResource<{
  created_by: string;
  created_on: string;
  changes: { at: string; by: string; lines: string[] }[];
}>({
  url: "helpdesk.api.crm_dashboard_settings.get_history",
  makeParams: () => ({ doctype: props.doctype, name: props.name }),
  auto: true,
});
watch(
  () => props.version,
  () => history.reload()
);

const all = ref(false);
const shown = computed(() =>
  (history.data?.changes || []).slice(0, all.value ? undefined : SHOWN)
);
</script>
